"""Multi-component agent: infer mechanisms from correlated observations, never labels."""
import json
from dataclasses import dataclass
from pathlib import Path

from app.agent import policy
from app.agent.agent import AgentRun, TraceStep
from app.communication.catalog import ROOTS, VERSION
from app.communication.correlation import BLOCKING_CONFLICT_CODES, correlate
from app.communication.storage import event_rows, get_session
from app.core.settings import category_ids
from app.models import CaseState, CheckResult, Complaint, DiagnosisResult, Evidence

CALIBRATION_FILE = Path(__file__).resolve().parents[1] / 'config' / 'communication_calibration.json'


def confidence_from(model, strength):
    if not model:
        return None
    return next(b['probability'] for b in model['bins'] if strength <= b['upper'])


@dataclass
class CommunicationRun:
    result: dict
    agent_run: AgentRun


class MultiComponentAgent:
    def __init__(self, conn, calibration=None, use_saved_calibration=True):
        from app.core.observations import observations
        self.conn = observations(conn)
        self.calibration = calibration
        if calibration is None and use_saved_calibration and CALIBRATION_FILE.exists():
            self.calibration = json.loads(CALIBRATION_FILE.read_text(encoding='utf-8'))
            if self.calibration.get('simulator_version') != VERSION:
                self.calibration = None

    def run(self, session_id, complaint=None):
        session = get_session(self.conn, session_id)
        observations = correlate(event_rows(self.conn, session_id))
        rows, anomalies = observations['events'], observations['anomalies']
        by_id = {e['event_id']: e for e in rows}
        kinds = {}
        for e in rows:
            kinds.setdefault(e['event_type'], []).append(e)
        complaint = complaint or Complaint(session['app_id'], 'Investigate the correlated charging request.',
            complaint_ts=session['ended_at'], session_ref=session_id, user_ref='USR-' + session_id,
            station_id=session['components']['charger'], data_origin='simulated')
        from app.core.observations import observation_complaint
        complaint = observation_complaint(complaint)
        state = CaseState(complaint, category_ids())
        legacy = self.conn.execute('SELECT * FROM charging_sessions WHERE session_id=?', (session_id,)).fetchone()
        state.matched_session = dict(legacy)
        run = AgentRun(state)
        candidates, evidence, disabled = [], [], []

        def add(root, description, ids, tool):
            ids = list(dict.fromkeys(i for i in ids if i in by_id))
            if not ids:
                return None
            category, component = ROOTS[root]
            signal = 'mc_' + root
            weight_row = self.conn.execute('SELECT weight,active FROM knowledge_rules WHERE signal_key=? AND category=? ORDER BY active DESC,rule_id LIMIT 1', (signal, category)).fetchone()
            if weight_row is not None and not weight_row['active']:
                disabled.append(root)
                return Evidence(kind='neutral', description='Rule disabled by reviewer; observed hypothesis requires manual verification: ' + description,
                                source_table='communication_events', source_ref=ids[0], tool_name=tool)
            weight = weight_row['weight'] if weight_row else .5
            item = {'root_cause': root, 'description': description, 'event_ids': ids,
                    'component_type': component, 'signal_key': signal, 'weight': weight, 'tool_name': tool}
            candidates.append(root)
            evidence.append(item)
            return Evidence(kind='matching', description=description, source_table='communication_events', source_ref=ids[0],
                supports_category=category, signal_key=signal, weight=weight, tool_name=tool)

        def transport():
            out = []
            for code, root in [('message_dropped', 'network_loss'), ('message_delayed', 'network_delay'), ('duplicate_receive', 'network_duplicate')]:
                matches = [a for a in anomalies if a['code'] == code]
                if matches:
                    out.append(add(root, matches[0]['description'], [i for a in matches for i in a['event_ids']], 'communication_transport'))
            return [e for e in out if e]

        def controller():
            out = []
            for fault in kinds.get('controller.watchdog_timeout', []):
                received = [e for e in rows if e['event_type'] == 'message.received' and e['correlation_id'] == fault['correlation_id'] and e['component_type'] == 'charger']
                if received and fault['component_type'] == 'charger':
                    out.append(add('charger_controller_timeout', 'The charger received its command, then its own controller watchdog expired before replying.',
                                   [received[0]['event_id'], fault['event_id']], 'communication_controller'))
            return [e for e in out if e]

        def physical():
            out = []
            for kind, root, stop in [('bms.fault', 'vehicle_bms_fault', 'PowerDeliveryStop'), ('connector.fault', 'connector_fault', 'HardwareSafetyStop')]:
                faults = kinds.get(kind, [])
                delivered_stop = [e for e in rows if e['event_type'] == 'message.received' and e['payload'].get('operation') == stop and e['component_type'] == 'charger']
                state_stops = [e for e in kinds.get('session.state_changed', []) if e['payload']['to'] in ('failed', 'stopped')]
                if faults and delivered_stop and state_stops:
                    out.append(add(root, f"{faults[0]['component_type']} reported {faults[0]['payload'].get('code')}; a matching safety stop reached the charger and energy delivery stopped.",
                        [faults[0]['event_id'], delivered_stop[0]['event_id'], state_stops[0]['event_id']], 'communication_physical'))
            return [e for e in out if e]

        def conflicts(group, codes):
            return [add(root, a['description'], a['event_ids'], group) for code, root in codes
                    for a in anomalies if a['code'] == code]

        groups = [
            ('communication_transport', transport, True),
            ('communication_controller', controller, bool(kinds.get('request.timeout') or kinds.get('controller.watchdog_timeout'))),
            ('communication_physical', physical, bool(kinds.get('battery.ready') or kinds.get('bms.fault') or kinds.get('connector.fault'))),
            ('communication_authorization', lambda: conflicts('communication_authorization', [('authorization_conflict', 'authorization_conflict')]), bool(kinds.get('authorization.decision'))),
            ('communication_availability', lambda: conflicts('communication_availability', [('availability_conflict', 'stale_availability')]), bool(kinds.get('charger.status'))),
            ('communication_billing', lambda: conflicts('communication_billing', [('payment_conflict', 'payment_conflict'), ('metering_billing_conflict', 'metering_mismatch')]), bool(kinds.get('invoice.created') or kinds.get('payment.result'))),
        ]
        priors = self.conn.execute('SELECT tool_name,AVG(usefulness_score) score FROM tool_priors GROUP BY tool_name').fetchall()
        usefulness = {r['tool_name']: r['score'] for r in priors}
        groups.sort(key=lambda g: (-usefulness.get(g[0], .5), g[0]))
        for name, check, relevant in groups:
            if not relevant:
                continue
            matching = [e for e in check() if e]
            result = CheckResult(name, 'ok', f'Inspected correlated {name.removeprefix("communication_")} observations.',
                evidence_items=matching, signals=[e.signal_key for e in matching if e.kind == 'matching' and e.signal_key])
            deltas = policy.update_beliefs(self.conn, state, result)
            state.evidence.extend(matching)
            state.checks_run.append(name)
            state.step_count += 1
            run.trace.append(TraceStep(state.step_count, name, 'Inspect relevant observed component records; order follows reviewer-learned tool usefulness.',
                [], {'session_id': session_id}, result.to_dict(), result.summary,
                {'belief_deltas': deltas, 'beliefs_after': state.belief_snapshot(), 'evidence_added': [e.to_dict() for e in matching]}, False))

        # Completion is positive evidence, requiring observed lifecycle and billing.
        transitions = {e['payload']['to'] for e in kinds.get('session.state_changed', [])}
        required = {'discovered', 'connected', 'authorized', 'charging', 'completed'}
        payment_ok = any(e['status'] == 'captured' for e in kinds.get('payment.result', []))
        required_operations = {'DiscoverChargers', 'Authorize', 'RequestStartTransaction', 'SessionSetupReq',
                               'ChargeParameterDiscoveryReq', 'PowerDeliveryReq', 'TransactionEvent.Started', 'TransactionEvent.Ended', 'PaymentCapture'}
        received_operations = {e['payload'].get('operation') for e in kinds.get('message.received', [])}
        healthy = (required <= transitions and required_operations <= received_operations and payment_ok
                   and bool(kinds.get('invoice.created')) and len(kinds.get('meter.sample', [])) >= 2
                   and all(f['status'] == 'delivered' for f in observations['flows']) and not anomalies)
        integrity_conflicts = [a for a in anomalies if a['code'] in BLOCKING_CONFLICT_CODES]
        uncertain = bool(integrity_conflicts)
        roots = sorted(set(candidates))
        if len(roots) == 1 and not uncertain:
            root, classification = roots[0], 'probable'
        elif not roots and healthy:
            root, classification = 'none', 'normal'
        else:
            root, classification = None, 'inconclusive'
        primary = ROOTS[root][0] if root else None
        if root == 'none':
            evidence.append({'root_cause': 'none', 'description': 'Observed authorization, power delivery, increasing metering, completion and successful payment agree.',
                'event_ids': [e['event_id'] for e in rows if e['event_type'] in ('session.state_changed', 'meter.sample', 'payment.result', 'invoice.created')],
                'component_type': None, 'signal_key': None, 'weight': .8, 'tool_name': 'communication_completion'})
            state.evidence.append(Evidence(kind='neutral', description=evidence[-1]['description'],
                source_table='communication_events', source_ref=evidence[-1]['event_ids'][0],
                tool_name='communication_completion', weight=.8))
        for conflict in integrity_conflicts:
            evidence.append({'root_cause': None, 'kind': 'conflicting', 'description': conflict['description'], 'event_ids': conflict['event_ids'],
                             'component_type': None, 'signal_key': None, 'weight': 0, 'tool_name': 'communication_completion'})
            state.evidence.append(Evidence(kind='conflicting', description=conflict['description'], source_table='communication_events',
                                           source_ref=conflict['event_ids'][0], tool_name='communication_completion'))
        support = [e for e in evidence if e['root_cause'] == root]
        if root == 'none':
            strength = .8
        elif root is not None and support:
            sources = {by_id[i]['component_type'] for e in support for i in e['event_ids']}
            strength = min(.95, .45 + .3 * sum(e['weight'] for e in support) / len(support) + .05 * min(3, len(sources)))
        else:
            strength = 0.0
        unresolved = [] if root is not None else ['A single root cause could not be established from the observed event sequence.']
        unresolved.extend('Conflicting observations: ' + a['description'] for a in integrity_conflicts)
        if len(roots) > 1:
            unresolved.append('Multiple mechanisms are observed: ' + ', '.join(roots))
        if disabled:
            unresolved.append('Reviewer-disabled rules require manual verification: ' + ', '.join(disabled))
        if not healthy and not roots:
            unresolved.append('Obtain missing receiver/response, component safety, lifecycle and payment observations before asserting a cause.')
        run.stop_reason = 'correlated_evidence_complete' if root is not None else 'insufficient_or_conflicting_observations'
        run.outcome = 'no_fault_established' if root == 'none' else 'fault_detected' if root else 'inconclusive'
        state.step_count += 1
        run.trace.append(TraceStep(state.step_count, 'communication_completion', 'Verify lifecycle continuity, metering and payment completion.', [],
            {'session_id': session_id}, {'status': 'ok', 'signals': [], 'evidence_items': [e.to_dict() for e in state.evidence if e.kind == 'conflicting' and e.tool_name == 'communication_completion']},
            'Conflicting observations prevent a unique diagnosis.' if uncertain else 'Completed normally.' if healthy else 'Normal completion not independently established.',
            {'beliefs_after': state.belief_snapshot()}, False))
        confidence = confidence_from(self.calibration, strength) if root is not None else None
        run.diagnosis = DiagnosisResult('probable' if primary else 'inconclusive', primary, [], strength,
            'moderate' if primary else 'insufficient', [], unresolved, run.stop_reason, confidence=confidence)
        result = {'session_id': session_id, 'root_cause': root, 'category': primary, 'classification': classification,
                  'component_type': ROOTS[root][1] if root else None,
                  'component_id': session['components'].get(ROOTS[root][1]) if root else None,
                  'evidence_strength': round(strength, 4), 'confidence': confidence,
                  'confidence_scope': 'Validation-calibrated synthetic decision confidence; abstentions have no root-cause probability.' if self.calibration else 'Uncalibrated evidence score; no probability model has been fitted.',
                  'evidence': evidence, 'unresolved_questions': unresolved, 'checks': [s.tool_name for s in run.trace],
                  'diagnostic_checks': len(run.trace),
                  'communication_failure_detected': any(a['code'] in ('message_dropped', 'message_delayed', 'duplicate_receive') for a in anomalies) or 'charger_controller_timeout' in roots,
                  'transport_failure_detected': any(a['code'] in ('message_dropped', 'message_delayed', 'duplicate_receive') for a in anomalies),
                  'observation_gap_detected': any(a['code'] in ('missing_receive','missing_response','orphan_receive') for a in anomalies),
                  'evidence_conflict_detected': uncertain,
                  'supported_root_causes': roots if not uncertain else [],
                  'candidate_root_causes': roots, 'stop_reason': run.stop_reason}
        return CommunicationRun(result, run)
