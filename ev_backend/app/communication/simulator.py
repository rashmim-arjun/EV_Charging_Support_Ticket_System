"""Deterministic causal simulation, using an event clock rather than wall-clock sleeps.

Messages are emitted by a component, transported, received and acknowledged.
State changes only follow delivered operations; duplicates are idempotent and
timeouts never create charging energy. This is not a protocol implementation.
"""
import hashlib
import json
import random
from datetime import datetime, timedelta, timezone

from app.communication.catalog import VERSION, SPLITS, ROOTS, templates
from app.communication.schema import Event, GenerateRequest, Injection


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':')).encode()).hexdigest()[:16]


class SessionSimulation:
    def __init__(self, run_id, template, seed, index, injections=()):
        self.template = template
        self.variant = template['variant']
        self.profile = template['scenario']
        self.identity = digest([run_id, template['template_id'], index])
        self.session_id = 'MC-' + self.identity
        self.trace_id = 'TRACE-' + self.identity
        self.rng = random.Random(int(digest([seed, template['template_id'], index]), 16))
        self.start = datetime(2026, 10, 1, tzinfo=timezone.utc) + timedelta(days=self.rng.randrange(30), seconds=self.rng.randrange(86400))
        self.clock = 0
        self.events = []
        self.components = {c: f'{c.upper()}-{self.identity}' for c in ('app', 'csms', 'charger', 'connector', 'vehicle', 'bms', 'payment', 'network')}
        self.state = 'idle'
        self.energy = 0.0
        self.soc = self.rng.uniform(25, 55)
        self.initial_soc = self.soc
        self.capacity = 60.0
        self.tariff = round(self.rng.uniform(12, 22), 2)
        self.amount = 0.0
        self.message_count = 0
        self.used = set()
        self.injections = [Injection.model_validate(i) for i in injections]
        op = template.get('operation')
        if self.profile in ('network_delay', 'network_loss', 'network_duplicate', 'charger_controller_timeout'):
            kind = {'network_delay': 'delay', 'network_loss': 'drop', 'network_duplicate': 'duplicate', 'charger_controller_timeout': 'timeout'}[self.profile]
            self.injections.insert(0, Injection(kind=kind, operation=op, delay_ms=(6000 + self.variant * 7000 + self.rng.randrange(1000))))
        self.fault_triggered = False

    def event(self, component, kind, status='ok', payload=None, severity='info', *, correlation=None, message_id=None, parent=None, message=None, attempt_id=None):
        row = Event(event_id=f'{self.session_id}-E{len(self.events):04d}', session_id=self.session_id,
            trace_id=self.trace_id, correlation_id=correlation or self.trace_id, message_id=message_id,attempt_id=attempt_id,
            parent_event_id=parent, component_id=self.components[component], component_type=component,
            timestamp=self.start + timedelta(milliseconds=self.clock), sequence=len(self.events),
            event_type=kind, severity=severity, status=status, message=message or kind.replace('.', ' '), payload=payload or {})
        self.events.append(row.model_dump(mode='json'))
        self.clock += 1
        return row.event_id

    def transition(self, target, reason):
        allowed = {'idle': {'discovered', 'failed'}, 'discovered': {'connected', 'failed'},
            'connected': {'authorized', 'failed'}, 'authorized': {'charging', 'failed'},
            'charging': {'stopped', 'completed'}, 'stopped': set(), 'completed': set(), 'failed': set()}
        if target not in allowed[self.state]:
            raise ValueError(f'Illegal charging transition {self.state} -> {target}')
        old, self.state = self.state, target
        self.event('charger', 'session.state_changed', target, {'from': old, 'to': target, 'reason': reason})

    def send(self, source, target, operation, payload=None, *, correlation=None, reply_to=None, acknowledge=True, reuse_message_id=None, attempt_id=None):
        self.message_count += 1
        mid = reuse_message_id or f'{self.session_id}-M{self.message_count:03d}'
        correlation = correlation or f'{self.trace_id}-C{self.message_count:03d}'
        data = dict(payload or {}, operation=operation, source=source, target=target,
                    deadline_ms=3000, reply_to=reply_to, expects_response=acknowledge)
        parent = self.event(source, 'message.sent', payload=data, correlation=correlation, message_id=mid,attempt_id=attempt_id)
        rule_index = next((i for i, r in enumerate(self.injections) if i not in self.used and r.operation == operation), None)
        rule = self.injections[rule_index] if rule_index is not None else None
        if rule:
            self.used.add(rule_index)
        if rule and rule.kind == 'retry':
            first_attempt = mid + '-A1'
            self.events[-1]['attempt_id'] = first_attempt
            self.clock += 100
            self.event('network','transport.dropped','lost',data,'error',correlation=correlation,message_id=mid,parent=parent,attempt_id=first_attempt)
            self.clock += rule.delay_ms
            self.event(source,'request.timeout','timeout',dict(data,request_message_id=mid),'warning',correlation=correlation,parent=parent,attempt_id=first_attempt)
            return self.send(source,target,operation,payload,correlation=correlation,reply_to=reply_to,acknowledge=acknowledge,
                             reuse_message_id=mid,attempt_id=mid+'-A2')
        delay = rule.delay_ms if rule and rule.kind == 'delay' else self.rng.randrange(20, 120)
        if rule and rule.kind == 'drop':
            self.clock += 100
            self.event('network', 'transport.dropped', 'lost', data, 'error', correlation=correlation, message_id=mid, parent=parent)
            self.clock += 3000
            self.event(source, 'request.timeout', 'timeout', dict(data, request_message_id=mid), 'error', correlation=correlation, parent=parent)
            return False
        self.clock += delay
        delivered = self.event('network', 'transport.delivered', 'delayed' if delay > 3000 else 'ok', dict(data, latency_ms=delay),
                               'warning' if delay > 3000 else 'info', correlation=correlation, message_id=mid, parent=parent,attempt_id=attempt_id)
        self.event(target, 'message.received', 'late' if delay > 3000 else 'ok', data, correlation=correlation, message_id=mid, parent=delivered,attempt_id=attempt_id)
        if rule and rule.kind == 'duplicate':
            for _ in range(rule.copies):
                self.clock += 10
                duplicate = self.event('network', 'transport.duplicated', 'duplicate', data, 'warning', correlation=correlation, message_id=mid, parent=parent)
                self.event(target, 'message.received', 'duplicate_ignored', data, 'warning', correlation=correlation, message_id=mid, parent=duplicate)
        if rule and rule.kind == 'timeout':
            self.clock += 3000
            self.event(target, 'controller.watchdog_timeout', 'faulted', dict(data, code='PROCESSOR_WATCHDOG'), 'error', correlation=correlation, parent=parent)
            self.event(source, 'request.timeout', 'timeout', dict(data, request_message_id=mid), 'error', correlation=correlation, parent=parent)
            return False
        if delay > 3000:
            # Delivery is observed, but the command expired before a state change.
            self.event(source, 'request.timeout', 'timeout', dict(data, request_message_id=mid, deadline_exceeded=True), 'error', correlation=correlation, parent=parent)
            return False
        if acknowledge:
            response_payload = {'accepted': True}
            if attempt_id:
                response_payload['reply_to_attempt'] = attempt_id
            return self.send(target, source, operation + '.response', response_payload, correlation=correlation, reply_to=mid, acknowledge=False)
        return True

    def fail(self, reason):
        if self.state == 'charging':
            self.transition('stopped', reason)
        elif self.state not in ('completed', 'stopped', 'failed'):
            self.transition('failed', reason)
        self.event('app', 'session.result', self.state, {'energy_kwh': self.energy, 'reason': reason}, 'warning')

    def bms_fault(self):
        codes = ['HV_INTERLOCK', 'BATTERY_OVER_TEMPERATURE', 'ISOLATION_FAULT']
        self.event('bms', 'bms.fault', 'faulted', {'code': codes[self.variant], 'soc': round(self.soc, 2), 'charging_permitted': False}, 'critical')
        self.send('bms', 'vehicle', 'BatterySafetyStop', {'charging_permitted': False})
        self.send('vehicle', 'charger', 'PowerDeliveryStop', {'reason': 'vehicle_safety_stop'})
        self.fault_triggered = True
        self.fail('vehicle_safety_stop')

    def connector_fault(self):
        codes = ['LATCH_NOT_LOCKED', 'CONTACTOR_OPENED', 'CONNECTOR_OVER_TEMPERATURE']
        self.event('connector', 'connector.fault', 'faulted', {'code': codes[self.variant], 'contactor_closed': False}, 'critical')
        self.send('connector', 'charger', 'HardwareSafetyStop', {'code': codes[self.variant]})
        self.fault_triggered = True
        self.fail('connector_safety_stop')

    def run(self):
        self.event('app', 'charging.requested', 'pending', {'station_id': self.components['charger'], 'requested_soc': 80})
        for c in self.components:
            self.event(c, 'component.health', 'connected', {'connection': 'online', 'health': 'ok'})
        if not self.send('app', 'csms', 'DiscoverChargers'):
            self.fail('discovery_timeout')
            return self.finish()
        self.event('charger', 'charger.status', 'available', {'revision': 2, 'observed_at': (self.start + timedelta(milliseconds=self.clock)).isoformat()})
        if not self.send('charger', 'csms', 'StatusNotification', {'status': 'available', 'revision': 2}):
            self.fail('status_publication_timeout')
            return self.finish()
        self.event('csms', 'availability.published', 'available', {'revision': 2, 'observed_at': (self.start + timedelta(milliseconds=self.clock)).isoformat()})
        self.event('app', 'availability.displayed', 'available', {'revision': 2})
        self.transition('discovered', 'charger_discovered')
        stale = self.profile == 'stale_availability' or any(r.kind == 'stale' for r in self.injections)
        if stale:
            self.event('connector', 'connector.occupied', 'occupied', {'revision': 3, 'vehicle_connected': True})
            self.event('charger', 'charger.status', 'occupied', {'revision': 3})
            self.event('csms', 'availability.published', 'available', {'revision': 2, 'age_ms': 60000 * (self.variant + 2), 'observed_at': (self.start - timedelta(minutes=self.variant + 2)).isoformat()}, 'warning')
            self.event('app', 'availability.displayed', 'available', {'revision': 2})
            self.fail('charger_occupied')
            return self.finish()
        self.send('vehicle', 'connector', 'CableConnected')
        self.event('connector', 'connector.connected', 'connected', {'vehicle_id': self.components['vehicle']})
        self.transition('connected', 'vehicle_connected')
        if self.profile == 'connector_fault' and self.variant == 0:
            self.connector_fault()
            return self.finish()
        # Split-specific underlying startup paths: remote-first, early vehicle
        # setup, and local authorization-first. All still gate power on approval.
        if self.variant == 1 and not self.send('charger', 'vehicle', 'SessionSetupReq'):
            self.fail('early_vehicle_setup_timeout')
            return self.finish()
        authorization_path = [('csms', 'charger', 'ConnectorLock'), ('csms', 'charger', 'SetChargingProfile'), ('charger', 'csms', 'Authorize')]
        if self.variant == 2:
            authorization_path = [authorization_path[2], authorization_path[0], authorization_path[1]]
        for source, target, op in authorization_path:
            if not self.send(source, target, op):
                self.fail('authorization_or_controller_timeout')
                return self.finish()
        if self.profile == 'authorization_conflict':
            self.event('csms', 'authorization.decision', 'rejected', {'reason': ['expired_token', 'revoked_token', 'unknown_token'][self.variant]}, 'warning')
            self.event('app', 'authorization.displayed', 'accepted', {'cached': True}, 'warning')
            self.fail('authorization_rejected')
            return self.finish()
        self.event('csms', 'authorization.decision', 'accepted', {'token_valid': True})
        self.event('app', 'authorization.displayed', 'accepted', {'cached': False})
        self.transition('authorized', 'authorization_accepted')
        if not self.send('csms', 'payment', 'PaymentHold', {'currency': 'INR', 'limit': 1000}):
            self.fail('payment_hold_timeout')
            return self.finish()
        self.event('payment', 'payment.hold', 'authorized', {'amount': 1000, 'currency': 'INR'})
        startup_path = [('csms', 'charger', 'RequestStartTransaction'), ('charger', 'vehicle', 'SessionSetupReq'),
                        ('charger', 'vehicle', 'ChargeParameterDiscoveryReq'), ('vehicle', 'bms', 'BatteryStatusRequest')]
        if self.variant == 1:
            startup_path = [p for p in startup_path if p[2] != 'SessionSetupReq']
        elif self.variant == 2:
            startup_path = [startup_path[1], startup_path[2], startup_path[3], startup_path[0]]
        for source, target, op in startup_path:
            if not self.send(source, target, op):
                self.fail('start_or_handshake_timeout')
                return self.finish()
        if self.profile == 'vehicle_bms_fault' and self.variant == 0:
            self.bms_fault()
            return self.finish()
        self.event('bms', 'battery.ready', 'ready', {'soc': round(self.soc, 2), 'capacity_kwh': self.capacity, 'charging_permitted': True})
        if not self.send('vehicle', 'charger', 'PowerDeliveryReq', {'ready': True}):
            self.fail('power_delivery_timeout')
            return self.finish()
        self.transition('charging', 'power_delivery_started')
        if not self.send('charger', 'csms', 'TransactionEvent.Started', {'sequence_number': 0}):
            self.fail('transaction_ack_timeout')
            return self.finish()
        count = 3 + self.variant
        interval_s = self.rng.randrange(180, 300)
        power_kw = self.rng.uniform(11, 50)
        initial_meter = round(self.rng.uniform(1000, 5000), 3)
        self.event('charger', 'meter.sample', 'charging', {'meter_kwh': initial_meter, 'energy_kwh': 0.0, 'power_kw': power_kw})
        for i in range(count):
            self.clock += interval_s * 1000
            self.energy = round(self.energy + power_kw * interval_s / 3600, 4)
            self.soc = self.initial_soc + self.energy / self.capacity * 100
            self.event('bms', 'battery.telemetry', 'charging', {'soc': round(self.soc, 3), 'temperature_c': round(28 + self.energy, 2)})
            self.event('vehicle', 'vehicle.charging', 'charging', {'energy_kwh': self.energy})
            self.event('charger', 'meter.sample', 'charging', {'meter_kwh': round(initial_meter + self.energy, 4), 'energy_kwh': self.energy, 'power_kw': round(power_kw, 3)})
            self.send('charger', 'csms', 'MeterValues', {'energy_kwh': self.energy, 'sequence_number': i + 1})
            if self.profile in ('vehicle_bms_fault', 'connector_fault') and i == self.variant - 1:
                self.bms_fault() if self.profile == 'vehicle_bms_fault' else self.connector_fault()
                break
        if self.state == 'charging':
            self.transition('completed', 'target_reached')
        if not self.send('charger', 'csms', 'TransactionEvent.Ended', {'energy_kwh': self.energy, 'reason': self.state}):
            return self.finish()
        invoice_energy = self.energy
        if self.profile == 'metering_mismatch':
            invoice_energy = round(self.energy * (1.15 + self.variant * .1), 4)
        self.amount = round(invoice_energy * self.tariff, 2)
        self.event('csms', 'invoice.created', 'pending', {'energy_kwh': invoice_energy, 'tariff_per_kwh': self.tariff, 'amount': self.amount, 'currency': 'INR'})
        if not self.send('csms', 'payment', 'PaymentCapture', {'amount': self.amount, 'currency': 'INR'}):
            return self.finish()
        if self.profile == 'payment_conflict':
            self.event('payment', 'payment.result', 'failed', {'amount': self.amount, 'reason': ['declined', 'processor_timeout', 'hold_expired'][self.variant]}, 'error')
            self.event('app', 'payment.displayed', 'captured', {'amount': self.amount, 'cached': True}, 'warning')
        else:
            self.event('payment', 'payment.result', 'captured', {'amount': self.amount, 'currency': 'INR'})
            self.event('app', 'payment.displayed', 'captured', {'amount': self.amount})
        available_status = 'faulted' if self.profile == 'connector_fault' else 'available'
        self.event('connector', 'connector.disconnected', available_status, {'vehicle_connected': False})
        self.event('charger', 'charger.status', available_status, {'revision': 4})
        self.event('csms', 'availability.published', available_status, {'revision': 4})
        self.event('app', 'session.result', self.state, {'energy_kwh': self.energy, 'amount': self.amount})
        return self.finish()

    def finish(self):
        expected = [{'event_type': e['event_type'], 'component_type': e['component_type'], 'message_id': e['message_id']}
                    for e in self.events]
        visible = self.events
        root = self.profile
        if root == 'inconclusive':
            # A genuine observability gap: the collector captures only intake,
            # never a fictitious completed session or unrelated positive faults.
            if self.variant == 0:
                visible = [e for e in self.events if e['event_type'] == 'charging.requested']
            elif self.variant == 1:
                visible = [e for e in self.events if e['event_type'] == 'charging.requested'
                           or (e['event_type'] == 'component.health' and e['component_type'] in ('app', 'csms'))
                           or (e['event_type'] == 'message.sent' and e['payload'].get('operation') == 'RequestStartTransaction')]
            else:
                visible = [e for e in self.events if e['event_type'] in ('charging.requested', 'connector.connected', 'authorization.displayed')
                           or (e['event_type'] == 'charger.status' and e['payload'].get('revision') == 2)
                           or (e['event_type'] == 'message.sent' and e['payload'].get('operation') == 'PowerDeliveryReq')]
            root = None
        # Custom injections can create overlapping mechanisms; the benchmark
        # uses the fixed catalogue only. Do not invent a single verified label.
        custom = len(self.injections) > int(self.profile in ('network_delay', 'network_loss', 'network_duplicate', 'charger_controller_timeout'))
        physical_root = 'none' if self.profile == 'inconclusive' else root
        triggered = [] if physical_root == 'none' else [physical_root]
        if custom:
            # Record what actually fired, rather than retaining the requested
            # profile when an earlier injected fault prevented that profile.
            triggered = set()
            profile_events = {'vehicle_bms_fault': 'bms.fault', 'connector_fault': 'connector.fault',
                              'authorization_conflict': 'authorization.decision', 'payment_conflict': 'payment.result',
                              'metering_mismatch': 'invoice.created'}
            if self.profile in profile_events and any(e['event_type'] == profile_events[self.profile] for e in self.events):
                triggered.add(self.profile)
            if any(e['event_type'] == 'connector.occupied' for e in self.events):
                triggered.add('stale_availability')
            for e in self.events:
                if e['event_type'] == 'transport.dropped':
                    triggered.add('network_loss')
                elif e['event_type'] == 'transport.duplicated':
                    triggered.add('network_duplicate')
                elif e['event_type'] == 'transport.delivered' and e['status'] == 'delayed':
                    triggered.add('network_delay')
                elif e['event_type'] == 'controller.watchdog_timeout':
                    triggered.add(e['component_type'] + '_controller_timeout')
            triggered = sorted(triggered)
            physical_root = triggered[0] if len(triggered) == 1 else 'none' if not triggered else None
        truth = {'root_cause': physical_root, 'root_causes': triggered, 'expected_label': self.profile if not custom else 'inconclusive',
                 'root_component_type': ROOTS.get(physical_root, (None, None))[1],
                 'affected_components': sorted({e['component_type'] for e in self.events if e['severity'] in ('error', 'critical', 'warning')}),
                 'expected_events': expected, 'template_id': self.template['template_id'], 'split': self.template['split'],
                 'fault_configuration': {'variant': self.variant, 'operation': self.template.get('operation'),
                    'injections': [r.model_dump() for r in self.injections]}, 'diagnosable': root is not None and not custom,
                 'physical_status': self.state, 'physical_energy_kwh': self.energy,
                 'diagnostic_event_ids': [e['event_id'] for e in self.events if e['severity'] in ('error', 'critical', 'warning') or e['event_type'] in ('session.state_changed', 'payment.result')],
                 'message_contracts': [{'message_id': e['message_id'], 'target': e['payload']['target'], 'deadline_ms': e['payload']['deadline_ms'],
                                       'expects_response': e['payload']['expects_response']} for e in self.events if e['event_type'] == 'message.sent'],
                 'unapplied_injections': [r.model_dump() for i, r in enumerate(self.injections) if i not in self.used and r.kind != 'stale']}
        visible_states = [e['payload']['to'] for e in visible if e['event_type'] == 'session.state_changed']
        return {'session_id': self.session_id, 'trace_id': self.trace_id, 'app_id': 'statiq',
                'started_at': self.start.isoformat(), 'ended_at': visible[-1]['timestamp'],
                'status': visible_states[-1] if visible_states else 'unknown', 'components': self.components, 'events': visible, 'truth': truth,
                'energy_kwh': self.energy, 'amount': self.amount}


def generate_dataset(request: GenerateRequest | dict):
    cfg = GenerateRequest.model_validate(request)
    selected = set(cfg.scenarios or ROOTS)
    if not selected or not selected <= set(ROOTS):
        raise ValueError('Unknown or empty scenario selection')
    run_id = 'RUN-' + digest([VERSION, cfg.model_dump(mode='json')])
    chosen = [t for t in templates() if t['scenario'] in selected and (cfg.split == 'all' or t['split'] == cfg.split)]
    sessions = [SessionSimulation(run_id, t, cfg.seed, i, cfg.injections).run()
                for t in chosen for i in range(cfg.per_template)]
    return {'run_id': run_id, 'version': VERSION, 'config': cfg.model_dump(mode='json'), 'sessions': sessions}
