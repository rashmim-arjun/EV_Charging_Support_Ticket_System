"""Reconstruct observations and anomalies without reading simulator annotations."""
from collections import defaultdict
from datetime import datetime
import json


# These invalidate a unique causal interpretation. Domain disagreements such
# as a stale app display are separately diagnosed when provenance is intact.
BLOCKING_CONFLICT_CODES = frozenset({
    'clock_or_order_conflict', 'receiver_identity_conflict', 'sender_identity_conflict',
    'orphan_receive', 'nonmonotonic_meter', 'state_conflict', 'message_content_conflict',
    'message_correlation_conflict', 'transport_outcome_conflict', 'response_conflict',
    'response_contract_conflict', 'authoritative_fact_conflict',
    'response_state_conflict',
})


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'))


def business_context(event):
    payload = event['payload']
    ids = {k: payload[k] for k in ('request_id', 'transaction_id', 'authorization_id', 'payment_id', 'invoice_id') if k in payload}
    return event['correlation_id'], canonical(ids)


def timestamp(value):
    return datetime.fromisoformat(value.replace('Z', '+00:00'))


def correlate(events):
    # Accept only the documented observation fields, never arbitrary truth fields.
    from app.communication.schema import Event
    rows = [Event.model_validate(e).model_dump(mode='json') for e in events]
    if len({e['session_id'] for e in rows}) > 1:
        raise ValueError('Correlation requires exactly one session')
    if len({e['trace_id'] for e in rows}) > 1:
        raise ValueError('Correlation requires one charging-request trace')
    if len({e['event_id'] for e in rows}) != len(rows):
        raise ValueError('Duplicate event IDs are invalid; duplicated messages need distinct event IDs')
    ordered = sorted(rows, key=lambda e: (timestamp(e['timestamp']), e['sequence'], e['event_id']))
    messages, correlations = defaultdict(list), defaultdict(list)
    for e in ordered:
        correlations[e['correlation_id']].append(e['event_id'])
        if e['message_id']:
            messages[(e['message_id'], e.get('attempt_id'))].append(e)
    anomalies, flows = [], []

    def anomaly(code, description, related, component=None, severity='warning', **extra):
        anomalies.append({'code': code, 'description': description, 'event_ids': [e['event_id'] for e in related],
                          'component_type': component, 'severity': severity, **extra})

    horizon = timestamp(ordered[-1]['timestamp']) if ordered else None
    conflicted_messages = set()
    for (mid, attempt_id), group in messages.items():
        sent = [e for e in group if e['event_type'] == 'message.sent']
        received = [e for e in group if e['event_type'] == 'message.received']
        drops = [e for e in group if e['event_type'] == 'transport.dropped']
        record = sent[0] if sent else group[0]
        data = record['payload']
        flow = {'message_id': mid, 'attempt_id': attempt_id, 'flow_id': mid + (':' + attempt_id if attempt_id else ''), 'correlation_id': record['correlation_id'], 'operation': data.get('operation'),
                'source': data.get('source'), 'target': data.get('target'), 'sent_at': sent[0]['timestamp'] if sent else None,
                'received_at': received[0]['timestamp'] if received else None, 'latency_ms': None,
                'status': 'delivered' if received else 'missing', 'event_ids': [e['event_id'] for e in group], 'reply_to': data.get('reply_to')}
        # Transport metadata (e.g. observed latency) may differ, but the actual
        # message body and exchange identity must survive delivery unchanged.
        wire = [e for e in group if e['event_type'] in ('message.sent', 'message.received')]
        transport = [e for e in group if e['event_type'].startswith('transport.')]
        conflicts = []
        transport_disagrees = any(k in e['payload'] and canonical(e['payload'][k]) != canonical(v)
                                  for e in transport for k, v in data.items())
        if len({canonical(e['payload']) for e in wire}) > 1 or transport_disagrees:
            conflicts.append(('message_content_conflict', 'Observations sharing one message ID disagree on operation, endpoints or message content.', group))
        if len({e['correlation_id'] for e in group}) > 1:
            conflicts.append(('message_correlation_conflict', 'One message ID is assigned to different request/response exchanges.', group))
        if any(e['component_type'] != e['payload'].get('source') for e in sent):
            conflicts.append(('sender_identity_conflict', 'The sending component differs from the declared message source.', sent))
        if any(e['component_type'] != e['payload'].get('target') for e in received):
            conflicts.append(('receiver_identity_conflict', 'The receiving component differs from the declared message target.', received))
        deliveries = [e for e in group if e['event_type'] in ('transport.delivered', 'transport.duplicated')]
        if drops and (received or deliveries):
            # The schema has no attempt identity. A retry is possible, but
            # cannot be assumed to reconcile incompatible transport claims.
            conflicts.append(('transport_outcome_conflict', 'The same message is recorded as dropped and delivered/received without an unambiguous transport attempt identity.', group))
        if conflicts:
            for code, description, related in conflicts:
                anomaly(code, description, related, severity='error', message_id=mid)
            conflicted_messages.add(mid)
            flow['status'] = 'conflicting'
            flows.append(flow)
            continue
        if drops:
            flow['status'] = 'dropped'
            anomaly('message_dropped', f"{data.get('operation')} was explicitly dropped by the transport.", group, 'network', 'error', message_id=mid)
        if sent and not received:
            age = (horizon - timestamp(sent[0]['timestamp'])).total_seconds() * 1000
            if drops or age >= data.get('deadline_ms', 3000):
                anomaly('missing_receive', f"No receiver observation for {data.get('operation')}.", sent + drops, 'network' if drops else None, message_id=mid)
            else:
                flow['status'] = 'pending'
        if received and not sent:
            anomaly('orphan_receive', 'A receive observation has no corresponding sender record.', received, None, message_id=mid)
        if sent and received:
            latency = (timestamp(received[0]['timestamp']) - timestamp(sent[0]['timestamp'])).total_seconds() * 1000
            flow['latency_ms'] = round(latency, 3)
            if latency < 0:
                anomaly('clock_or_order_conflict', 'A receive timestamp precedes its send timestamp.', sent + received, None, 'error', message_id=mid)
            elif latency > data.get('deadline_ms', 3000):
                flow['status'] = 'delayed'
                anomaly('message_delayed', f"{data.get('operation')} exceeded its observed request deadline ({latency:.0f} ms).", sent + received[:1], 'network', 'error', message_id=mid)
            if len(received) > 1:
                flow['status'] = 'duplicated'
                anomaly('duplicate_receive', f'{len(received)} receives share one message ID; idempotent receivers must avoid repeated side effects.', sent + received, 'network', message_id=mid)
            if data.get('expects_response'):
                replies = [e for e in ordered if e['event_type'] == 'message.sent' and e['payload'].get('reply_to') == mid
                           and e['correlation_id'] == record['correlation_id']]
                age = (horizon - timestamp(sent[0]['timestamp'])).total_seconds() * 1000
                if not replies and age >= data.get('deadline_ms', 3000):
                    anomaly('missing_response', f"{data.get('operation')} was received but has no response record.", sent + received[:1], None, message_id=mid)
        flows.append(flow)

    # A reply must belong to the declared request, reverse its endpoints and
    # answer its operation. Merely sharing a correlation ID is insufficient.
    replies = defaultdict(list)
    for e in ordered:
        if e['event_type'] != 'message.sent':
            continue
        if not e['payload'].get('reply_to'):
            if str(e['payload'].get('operation', '')).endswith('.response'):
                anomaly('response_contract_conflict', 'A response has no request identity in reply_to.', [e], severity='error', message_id=e['message_id'])
                conflicted_messages.add(e['message_id'])
            continue
        request_id = e['payload']['reply_to']
        requests = [r for (message_id, attempt_id), group in messages.items() if message_id == request_id
                    and (not e['payload'].get('reply_to_attempt') or attempt_id == e['payload']['reply_to_attempt'])
                    for r in group if r['event_type'] == 'message.sent' and r['correlation_id'] == e['correlation_id']]
        reply = e['payload']
        if not requests:
            anomaly('response_contract_conflict', 'A response refers to a request with no sender observation.', [e], severity='error', message_id=e['message_id'])
            conflicted_messages.add(e['message_id'])
        else:
            request = requests[0]
            contract = request['payload']
            if (e['correlation_id'] != request['correlation_id'] or reply.get('source') != contract.get('target')
                    or reply.get('target') != contract.get('source')
                    or reply.get('operation') != str(contract.get('operation')) + '.response'):
                anomaly('response_contract_conflict', 'A response contradicts its request operation, endpoints or correlation ID.',
                        requests + [e], severity='error', message_id=e['message_id'])
                conflicted_messages.update([request_id, e['message_id']])
        replies[(request_id, e['payload'].get('reply_to_attempt'), e['correlation_id'])].append(e)
    for (request_id, attempt_id, correlation_id), responses in replies.items():
        if len({canonical(e['payload']) for e in responses}) > 1:
            anomaly('response_conflict', 'One request has incompatible response contents; no authoritative response can be selected.',
                    responses, severity='error', message_id=request_id)
            conflicted_messages.update([request_id, *(e['message_id'] for e in responses)])
    startup_operations = {'ConnectorLock', 'SetChargingProfile', 'RequestStartTransaction', 'SessionSetupReq',
                          'ChargeParameterDiscoveryReq', 'PowerDeliveryReq'}
    for response in ordered:
        if response['event_type'] != 'message.received' or response['payload'].get('accepted') is not False:
            continue
        p = response['payload']
        operation = str(p.get('operation', '')).removesuffix('.response')
        if not p.get('reply_to'):
            continue
        later = [e for e in ordered if timestamp(e['timestamp']) >= timestamp(response['timestamp'])]
        if operation == 'Authorize':
            incompatible = [e for e in later if e['event_type'] == 'session.state_changed'
                            and e['payload'].get('to') in ('authorized', 'charging', 'completed')]
        elif operation in startup_operations:
            incompatible = [e for e in later if e['event_type'] == 'session.state_changed'
                            and e['payload'].get('to') == 'charging']
        elif operation == 'PaymentCapture':
            incompatible = [e for e in later if e['event_type'] == 'payment.result' and e['status'] == 'captured']
        else:
            incompatible = []
        def accepted_retry_before(outcome):
            return any(e['event_type'] == 'message.received' and e['payload'].get('accepted') is True
                       and e['payload'].get('operation') == p.get('operation')
                       and e['payload'].get('source') == p.get('source') and e['payload'].get('target') == p.get('target')
                       and e['payload'].get('reply_to')
                       and (e['payload']['reply_to'], e['payload'].get('reply_to_attempt')) != (p['reply_to'], p.get('reply_to_attempt'))
                       and e['payload']['reply_to'] not in conflicted_messages and e['message_id'] not in conflicted_messages
                       and timestamp(response['timestamp']) < timestamp(e['timestamp']) <= timestamp(outcome['timestamp'])
                       for e in ordered)
        incompatible = [e for e in incompatible if not accepted_retry_before(e)]
        if incompatible:
            anomaly('response_state_conflict', 'A rejected request is followed by a successful outcome that requires its acceptance.',
                    [response, *incompatible], severity='error', message_id=response['message_id'])
            conflicted_messages.update([p['reply_to'], response['message_id']])
    conflicted_messages.update(a['message_id'] for a in anomalies if a['code'] in BLOCKING_CONFLICT_CODES and a.get('message_id'))
    for flow in flows:
        if flow['message_id'] in conflicted_messages:
            flow['status'] = 'conflicting'
    # Do not turn a contradictory exchange into an asserted transport fault.
    anomalies = [a for a in anomalies if a.get('message_id') not in conflicted_messages
                 or a['code'] in BLOCKING_CONFLICT_CODES]

    def of(kind):
        return [e for e in ordered if e['event_type'] == kind]

    # Compare terminal facts only within the same explicit business context.
    # Revision/sample identity prevents legitimate later status/meter updates
    # from being mistaken for contradictory assertions about the same fact.
    fact_groups = defaultdict(list)
    for e in ordered:
        kind, p = e['event_type'], e['payload']
        scope = (e['component_id'], kind, *business_context(e))
        if kind == 'authorization.decision' and e['status'] in ('accepted', 'rejected'):
            fact_groups[scope].append((e, canonical(e['status'])))
        elif kind == 'payment.result' and e['status'] in ('captured', 'failed'):
            fact_groups[scope].append((e, canonical([e['status'], p.get('amount'), p.get('currency')])))
        elif kind in ('charger.status', 'availability.published') and 'revision' in p:
            fact_groups[(*scope, canonical(p['revision']))].append((e, canonical(e['status'])))
        elif kind == 'invoice.created':
            fact_groups[(*scope, canonical(p.get('revision')))].append((e, canonical([p.get('energy_kwh'), p.get('tariff_per_kwh'), p.get('amount'), p.get('currency')])))
        elif kind == 'meter.sample':
            sample = p.get('sample_id', timestamp(e['timestamp']).isoformat())
            fact_groups[(*scope, canonical(sample))].append((e, canonical([p.get('meter_kwh'), p.get('energy_kwh')])))
    for claims in fact_groups.values():
        if len({signature for _, signature in claims}) > 1:
            related = [e for e, _ in claims]
            anomaly('authoritative_fact_conflict', f"The same component asserts incompatible {related[0]['event_type']} facts in one business context/revision.",
                    related, severity='error')

    for authoritative_kind, display_kind, code, description, component in [
        ('authorization.decision', 'authorization.displayed', 'authorization_conflict', 'App authorization display conflicts with the CSMS decision.', 'app'),
        ('payment.result', 'payment.displayed', 'payment_conflict', 'App payment display conflicts with the payment-service result.', 'payment'),
        ('charger.status', 'availability.published', 'availability_conflict', 'Published availability conflicts with the charger snapshot.', 'csms'),
    ]:
        authoritative = {business_context(e): e for e in of(authoritative_kind)}
        displayed = {business_context(e): e for e in of(display_kind)}
        for context in sorted(authoritative.keys() & displayed.keys()):
            actual, shown = authoritative[context], displayed[context]
            if actual['status'] != shown['status']:
                anomaly(code, description, [actual, shown], component, 'error')
    invoices, meters = of('invoice.created'), of('meter.sample')
    if invoices and len(meters) >= 2:
        measured = meters[-1]['payload'].get('meter_kwh', 0) - meters[0]['payload'].get('meter_kwh', 0)
        billed = invoices[-1]['payload'].get('energy_kwh', 0)
        if abs(measured - billed) > .02:
            anomaly('metering_billing_conflict', f'Meter delta {measured:.4f} kWh differs from invoiced {billed:.4f} kWh.',
                    [meters[0], meters[-1], invoices[-1]], 'csms', 'error')
        if any(b['payload'].get('meter_kwh', 0) < a['payload'].get('meter_kwh', 0) for a, b in zip(meters, meters[1:])):
            anomaly('nonmonotonic_meter', 'Cumulative meter readings decreased.', meters, None, 'error')
    states = of('session.state_changed')
    for previous, current in zip(states, states[1:]):
        if previous['payload'].get('to') != current['payload'].get('from'):
            anomaly('state_conflict', 'Session state transitions do not form a continuous chain.', [previous, current], None, 'error')

    components = {}
    for e in ordered:
        c = e['component_type']
        state = components.setdefault(c, {'component_type': c, 'component_id': e['component_id'], 'health': 'unknown',
                                          'connection': 'unknown', 'last_seen': e['timestamp'], 'error_count': 0})
        state['last_seen'] = e['timestamp']
        if e['event_type'] == 'component.health':
            state['connection'] = e['payload'].get('connection', 'unknown')
            state['health'] = e['payload'].get('health', 'unknown')
        if e['severity'] in ('error', 'critical'):
            state['error_count'] += 1
            state['health'] = 'faulted' if e['status'] == 'faulted' else 'degraded'
        if e['event_type'] == 'transport.dropped':
            state['connection'] = 'message_loss'
        elif e['event_type'] == 'transport.delivered' and e['status'] == 'delayed' and state['connection'] != 'message_loss':
            state['connection'] = 'delayed'
    for a in anomalies:
        c = a['component_type']
        if c not in components:
            continue
        state = components[c]
        state['anomaly_count'] = state.get('anomaly_count', 0) + 1
        if state['health'] != 'faulted':
            state['health'] = 'degraded'
        if a['code'] == 'duplicate_receive' and state['connection'] == 'online':
            state['connection'] = 'duplicate_messages'
    by_id = {e['event_id']: e for e in ordered}
    for a in anomalies:
        if a['code'] not in BLOCKING_CONFLICT_CODES:
            continue
        for c in {by_id[i]['component_type'] for i in a['event_ids']}:
            components[c]['health'] = 'unknown'
            components[c]['connection'] = 'conflicting_observations'
            components[c]['observation_conflict'] = True
    return {'events': ordered, 'flows': flows, 'anomalies': anomalies,
            'correlations': dict(correlations), 'components': list(components.values()),
            'observed_components': len(components), 'scope': 'Health and connection states reflect observations during this simulated session, not live equipment.'}
