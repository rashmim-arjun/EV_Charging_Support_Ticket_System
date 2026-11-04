"""Negative and audit tests: weak evidence must not yield a confident assignment."""
from app.research.experiment import evaluate_research
from app.services.tickets import decide

CLAIMED = {'classification': 'probable', 'category': 'payment_or_billing_failure', 'root_cause': 'payment_conflict',
           'component_type': 'payment', 'unresolved_questions': []}


def _ticket(client, root, complaint, with_session=True):
    body = {'app_id': 'statiq', 'complaint_text': complaint, 'data_origin': 'simulated'}
    if with_session:
        sid = client.post('/api/v1/communication/generate', json={'scenarios': [root], 'per_template': 1}).json()['session_ids'][0]
        body['session_ref'] = sid
    response = client.post('/api/v1/cases', json=body)
    assert response.status_code == 201, response.text
    return response.json()['case']['ticket']


def test_confident_label_without_cited_log_evidence_is_not_routed_to_a_specialist():
    for evidence in ([], [{'description': 'complaint wording only', 'source_table': 'cases'}]):
        decision = decide({**CLAIMED, 'evidence': evidence}, (), 'I was charged twice for this visit.')
        assert decision['assigned_team'] == 'triage'
        assert decision['classification'] == 'inconclusive'
        assert decision['originating_component'] is None
        assert decision['requires_human_review']


def test_complaint_wording_cannot_override_contrary_component_logs(client):
    ticket = _ticket(client, 'connector_fault', 'I was charged twice and my refund is missing. This is a payment problem.')
    assert ticket['assigned_team'] == 'charger_maintenance'
    assert ticket['decision']['classification'] == 'connector_or_charger_hardware_fault'
    assert ticket['decision']['evidence'], 'assignment must cite event IDs and timestamps'
    assert all(e['event_id'] and e['timestamp'] for e in ticket['decision']['evidence'])


def test_payment_complaint_without_any_logs_goes_to_triage_not_payment_support(client):
    ticket = _ticket(client, None, 'I was charged twice and I need a refund immediately.', with_session=False)
    assert ticket['assigned_team'] == 'triage'
    assert ticket['decision']['classification'] == 'inconclusive'
    assert ticket['decision']['originating_component'] is None


def test_insufficient_evidence_is_never_assigned_to_a_specialist_in_the_support_challenge():
    report = evaluate_research(repeats=1, development_only=True)
    outcomes = report['support_workflow']['outcomes']
    insufficient = [o for o in outcomes if o['expected']['assigned_team'] == 'triage' and o['expected']['classification'] == 'inconclusive']
    assert insufficient, 'challenge must contain insufficient-evidence tickets'
    assert all(o['decision']['assigned_team'] == 'triage' and o['decision']['classification'] == 'inconclusive' for o in insufficient)
    safety = [o for o in outcomes if o['expected']['priority'] in ('P0', 'P1')]
    assert all(o['decision']['requires_escalation'] for o in safety)
    assert all(o['decision']['delivery_scope'].startswith('Local') for o in outcomes)


def test_reviewer_correction_is_audited_and_unverified_prediction_is_not_learned(client):
    ticket = _ticket(client, 'connector_fault', 'The session ended early; please investigate.')
    cid = ticket['case_id']
    assert ticket['decision']['classification'] == 'connector_or_charger_hardware_fault'
    assert client.post(f'/api/v1/cases/{cid}/learning/preview').status_code in (404, 409, 422)
    resolution = client.post(f'/api/v1/cases/{cid}/resolution', json={'reviewer_id': 'rev-001',
        'verified_root_cause': 'payment_or_billing_failure', 'corrective_action': 'Reviewer found the billing record was wrong.'})
    assert resolution.status_code == 201, resolution.text
    latest = client.get('/api/v1/tickets/' + cid).json()
    entry = latest['history'][-1]
    assert entry['action'] == 'resolved' and entry['actor'] == 'rev-001'
    assert entry['after']['reviewer_correction'] is True
    assert entry['after']['system_classification_before_review'] == 'connector_or_charger_hardware_fault'
    assert latest['decision']['verified_classification'] == 'payment_or_billing_failure'


def test_queue_summary_counts_open_work_and_states_local_scope(client):
    _ticket(client, 'vehicle_bms_fault', 'My charging stopped early.')
    _ticket(client, None, 'Charging did not start and I have no session reference.', with_session=False)
    data = client.get('/api/v1/tickets/summary').json()
    assert data['total'] == 2
    assert sum(data['by_state'].values()) == 2
    assert sum(data['open_by_priority'].values()) == 2 and sum(data['open_by_team'].values()) == 2
    assert data['open_in_triage'] >= 1 and data['open_by_team'].get('vehicle_specialists') == 1
    assert data['delivery_scope'].startswith('Local')
