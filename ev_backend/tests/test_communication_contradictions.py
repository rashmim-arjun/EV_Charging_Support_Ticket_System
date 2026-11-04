"""Conflicting observations must not become confident transport/component diagnoses."""
import copy
import json
from datetime import datetime, timedelta
import pytest

from app.communication.correlation import correlate
from app.communication.diagnosis import MultiComponentAgent
from app.communication.simulator import generate_dataset
from app.communication.storage import persist_dataset


def session_data(root='none'):
    data = generate_dataset({'seed': 715, 'per_template': 1, 'split': 'test', 'scenarios': [root]})
    return data, data['sessions'][0]


def append_event(session, original, **changes):
    event = copy.deepcopy(original)
    event.update(event_id=f"{session['session_id']}-extra-{len(session['events'])}",
                 sequence=max(e['sequence'] for e in session['events']) + 1)
    event.update(changes)
    session['events'].append(event)
    return event


def assert_abstains(conn, data, code, ids):
    session = data['sessions'][0]
    report = correlate(session['events'])
    conflicts = [a for a in report['anomalies'] if a['code'] == code]
    assert conflicts, report['anomalies']
    assert set(ids) <= {i for a in conflicts for i in a['event_ids']}
    assert correlate(list(reversed(session['events']))) == report
    persist_dataset(conn, data)
    run = MultiComponentAgent(conn).run(session['session_id'])
    result = run.result
    assert result['classification'] == 'inconclusive'
    assert result['root_cause'] is None and result['component_type'] is None
    assert result['confidence'] is None and result['evidence_strength'] == 0
    assert any('conflict' in q.lower() for q in result['unresolved_questions'])
    assert set(ids) <= {i for e in result['evidence'] for i in e['event_ids']}
    assert run.agent_run.diagnosis.classification == 'inconclusive'
    return report, result


@pytest.mark.parametrize('field,value', [('operation', 'UnrelatedOperation'), ('source', 'payment'),
    ('target', 'app'), ('accepted', False)])
def test_same_message_id_with_different_content_is_not_a_healthy_session(conn, field, value):
    data, session = session_data()
    received = next(e for e in session['events'] if e['event_type'] == 'message.received'
                    and e['payload']['operation'] == 'Authorize.response')
    sent = next(e for e in session['events'] if e['event_type'] == 'message.sent' and e['message_id'] == received['message_id'])
    received['payload'][field] = value
    assert_abstains(conn, data, 'message_content_conflict', [sent['event_id'], received['event_id']])


def test_drop_and_receive_for_one_attempt_are_conflicting_not_network_loss(conn):
    data, session = session_data()
    delivered = next(e for e in session['events'] if e['event_type'] == 'transport.delivered')
    dropped = append_event(session, delivered, event_type='transport.dropped', status='lost', severity='error')
    report, result = assert_abstains(conn, data, 'transport_outcome_conflict', [delivered['event_id'], dropped['event_id']])
    flow = next(f for f in report['flows'] if f['message_id'] == dropped['message_id'])
    assert flow['status'] == 'conflicting'
    assert not result['transport_failure_detected']


def test_changed_duplicate_is_a_content_conflict_not_a_network_duplicate(conn):
    data, session = session_data('network_duplicate')
    duplicate = next(e for e in session['events'] if e['event_type'] == 'message.received' and e['status'] == 'duplicate_ignored')
    original = next(e for e in session['events'] if e['event_type'] == 'message.received'
                    and e['message_id'] == duplicate['message_id'] and e['status'] != 'duplicate_ignored')
    duplicate['payload']['amount'] = 99999
    _, result = assert_abstains(conn, data, 'message_content_conflict', [original['event_id'], duplicate['event_id']])
    assert 'network_duplicate' not in result['candidate_root_causes']


def test_one_message_cannot_change_correlation_id(conn):
    data, session = session_data()
    received = next(e for e in session['events'] if e['event_type'] == 'message.received')
    sent = next(e for e in session['events'] if e['event_type'] == 'message.sent' and e['message_id'] == received['message_id'])
    received['correlation_id'] = 'unrelated-exchange'
    assert_abstains(conn, data, 'message_correlation_conflict', [sent['event_id'], received['event_id']])


@pytest.mark.parametrize('field,value', [('operation', 'DifferentOperation.response'), ('correlation_id', 'other-exchange'),
                                       ('reply_to', 'absent-request'), ('reply_to', None)])
def test_response_must_match_request_contract(conn, field, value):
    data, session = session_data()
    response = next(e for e in session['events'] if e['event_type'] == 'message.sent' and e['payload'].get('reply_to'))
    for e in session['events']:
        if e['message_id'] == response['message_id']:
            if field == 'correlation_id':
                e[field] = value
            else:
                e['payload'][field] = value
    assert_abstains(conn, data, 'response_contract_conflict', [response['event_id']])


def test_incompatible_responses_do_not_silently_choose_the_first_response(conn):
    data, session = session_data()
    response = next(e for e in session['events'] if e['event_type'] == 'message.sent' and e['payload'].get('reply_to'))
    group = [e for e in session['events'] if e['message_id'] == response['message_id']]
    added = []
    for e in group:
        payload = dict(e['payload'], accepted=False)
        added.append(append_event(session, e, message_id='second-response', payload=payload))
    assert_abstains(conn, data, 'response_conflict', [response['event_id'], added[0]['event_id']])


@pytest.mark.parametrize('kind,changes', [
    ('authorization.decision', {'status': 'rejected'}),
    ('payment.result', {'status': 'failed'}),
    ('charger.status', {'status': 'occupied'}),
    ('availability.published', {'status': 'occupied'}),
    ('invoice.created', {'payload_field': 'amount'}),
    ('meter.sample', {'payload_field': 'meter_kwh'}),
])
def test_incompatible_authoritative_facts_are_not_resolved_by_latest_event(conn, kind, changes):
    data, session = session_data()
    original = next(e for e in session['events'] if e['event_type'] == kind)
    if 'payload_field' in changes:
        payload = dict(original['payload'])
        payload[changes['payload_field']] += 2
        changes = {'payload': payload}
    added = append_event(session, original, **changes)
    assert_abstains(conn, data, 'authoritative_fact_conflict', [original['event_id'], added['event_id']])


def test_identical_reobservations_and_new_status_revisions_are_not_conflicts(conn):
    data, session = session_data()
    for kind in ('authorization.decision', 'payment.result', 'charger.status', 'invoice.created', 'meter.sample'):
        original = next(e for e in session['events'] if e['event_type'] == kind)
        append_event(session, original)
    # Existing normal data also has available revision 2 followed by revision 4.
    assert not correlate(session['events'])['anomalies']
    persist_dataset(conn, data)
    assert MultiComponentAgent(conn).run(session['session_id']).result['classification'] == 'normal'


def test_independent_positive_fault_does_not_override_conflicting_observations(conn):
    data, session = session_data('vehicle_bms_fault')
    response = next(e for e in session['events'] if e['event_type'] == 'message.received' and e['payload'].get('accepted'))
    sent = next(e for e in session['events'] if e['event_type'] == 'message.sent' and e['message_id'] == response['message_id'])
    response['payload']['accepted'] = False
    _, result = assert_abstains(conn, data, 'message_content_conflict', [sent['event_id'], response['event_id']])
    assert 'vehicle_bms_fault' in result['candidate_root_causes']


@pytest.mark.parametrize('operation', ['Authorize', 'PowerDeliveryReq', 'PaymentCapture'])
def test_consistently_rejected_response_contradicts_successful_lifecycle(conn, operation):
    data, session = session_data()
    response = next(e for e in session['events'] if e['event_type'] == 'message.received'
                    and e['payload'].get('operation') == operation + '.response')
    for e in session['events']:
        if e['message_id'] == response['message_id']:
            e['payload']['accepted'] = False
    assert_abstains(conn, data, 'response_state_conflict', [response['event_id']])


def test_rejected_request_followed_by_a_distinct_accepted_retry_can_complete(conn):
    data, session = session_data()
    response = next(e for e in session['events'] if e['event_type'] == 'message.received'
                    and e['payload'].get('operation') == 'Authorize.response')
    original_request = response['payload']['reply_to']
    group = [copy.deepcopy(e) for e in session['events'] if e['message_id'] in (original_request, response['message_id'])]
    for e in session['events']:
        if e['message_id'] == response['message_id']:
            e['payload']['accepted'] = False
    when = datetime.fromisoformat(response['timestamp'])
    for index, e in enumerate(group, 1):
        payload = dict(e['payload'])
        if payload.get('reply_to') == original_request:
            payload['reply_to'] = 'retry-request'
        append_event(session, e, message_id='retry-request' if e['message_id'] == original_request else 'retry-response',
                     correlation_id='retry-exchange', payload=payload, timestamp=(when + timedelta(microseconds=index)).isoformat())
    assert not correlate(session['events'])['anomalies']
    persist_dataset(conn, data)
    assert MultiComponentAgent(conn).run(session['session_id']).result['classification'] == 'normal'


def test_transport_cannot_claim_another_message_body(conn):
    data, session = session_data()
    delivered = next(e for e in session['events'] if e['event_type'] == 'transport.delivered')
    sent = next(e for e in session['events'] if e['event_type'] == 'message.sent' and e['message_id'] == delivered['message_id'])
    delivered['payload']['operation'] = 'DifferentOperation'
    assert_abstains(conn, data, 'message_content_conflict', [sent['event_id'], delivered['event_id']])


def test_business_claims_for_distinct_requests_are_not_contradictions(conn):
    data, session = session_data()
    authorization = next(e for e in session['events'] if e['event_type'] == 'authorization.decision')
    displayed = next(e for e in session['events'] if e['event_type'] == 'authorization.displayed')
    for e in (authorization, displayed):
        e['payload']['request_id'] = 'accepted-request'
    rejected = append_event(session, authorization, status='rejected', payload={'request_id': 'other-request'})
    append_event(session, displayed, status='rejected', payload={'request_id': 'other-request'}, timestamp=rejected['timestamp'])
    assert not correlate(session['events'])['anomalies']
    persist_dataset(conn, data)
    assert MultiComponentAgent(conn).run(session['session_id']).result['classification'] == 'normal'


def test_public_api_and_linked_case_preserve_conflicting_evidence(client):
    from app.core.db import connect
    response = client.post('/api/v1/communication/generate', json={'seed': 19, 'per_template': 1, 'scenarios': ['none']})
    sid = response.json()['session_ids'][0]
    conn = connect()
    try:
        row = conn.execute("SELECT event_id,payload_json FROM communication_events WHERE session_id=? AND event_type='message.received' LIMIT 1", (sid,)).fetchone()
        payload = json.loads(row['payload_json'])
        payload['operation'] = 'CorruptedOperation'
        conn.execute('UPDATE communication_events SET payload_json=? WHERE event_id=?', (json.dumps(payload), row['event_id']))
        conn.commit()
    finally:
        conn.close()
    detail = client.get('/api/v1/communication/sessions/' + sid).json()
    assert any(f['status'] == 'conflicting' for f in detail['flows'])
    assert any(c.get('observation_conflict') and c['connection'] == 'conflicting_observations' for c in detail['components'])
    result = client.post(f'/api/v1/communication/sessions/{sid}/diagnose').json()
    assert result['classification'] == 'inconclusive' and result['confidence'] is None
    assert result['case_id']
    saved = client.get('/api/v1/communication/sessions/' + sid).json()['diagnosis']
    assert saved == result
    assert any(e.get('kind') == 'conflicting' and row['event_id'] in e['event_ids'] for e in saved['evidence'])
    case = client.get('/api/v1/cases/' + result['case_id']).json()
    assert case['diagnosis']['classification'] == 'inconclusive'
    assert case['diagnosis']['confidence'] is None
    references = {i for e in saved['evidence'] if e.get('kind') == 'conflicting' for i in e['event_ids']}
    assert any(e['source_table'] == 'communication_events' and e['source_ref'] in references
               for e in case['evidence']['conflicting'])
