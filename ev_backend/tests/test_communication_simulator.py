import copy
import json
from collections import defaultdict
from datetime import datetime
import pytest

from app.communication.catalog import templates, ROOTS
from app.communication.correlation import correlate
from app.communication.diagnosis import MultiComponentAgent
from app.communication.schema import Event, GenerateRequest
from app.communication.simulator import generate_dataset
from app.communication.storage import persist_dataset, event_rows
from app.communication.service import diagnose_session
from app.data.synthetic_generator import SyntheticDataset, reset_simulated_rows
from app.services import feedback


def dataset(root='none', split='test', injections=None):
    return generate_dataset({'seed': 127, 'per_template': 1, 'split': split, 'scenarios': [root], 'injections': injections or []})


def test_successful_lifecycle_is_causal_and_billing_balances():
    for split in ('train', 'validation', 'test'):
        s = dataset(split=split)['sessions'][0]
        report = correlate(s['events'])
        assert s['status'] == 'completed' and not report['anomalies']
        assert report['observed_components'] == 8
        states = [e['payload']['to'] for e in s['events'] if e['event_type'] == 'session.state_changed']
        assert states == ['discovered', 'connected', 'authorized', 'charging', 'completed']
        meter = [e for e in s['events'] if e['event_type'] == 'meter.sample']
        bill = next(e for e in s['events'] if e['event_type'] == 'invoice.created')
        assert bill['payload']['energy_kwh'] == pytest.approx(meter[-1]['payload']['energy_kwh'])
        assert s['amount'] == round(bill['payload']['energy_kwh'] * bill['payload']['tariff_per_kwh'], 2)
        assert all(datetime.fromisoformat(e['timestamp']).tzinfo for e in s['events'])


@pytest.mark.parametrize('root', list(ROOTS))
def test_catalogue_ground_truth_and_diagnosis(conn, root):
    for split in ('train', 'validation', 'test'):
        d = dataset(root, split)
        persist_dataset(conn, d)
        result = MultiComponentAgent(conn).run(d['sessions'][0]['session_id']).result
        assert result['root_cause'] == (None if root == 'inconclusive' else root)
        assert result['diagnostic_checks'] <= 8
        event_ids = {e['event_id'] for e in d['sessions'][0]['events']}
        assert all(set(e['event_ids']) <= event_ids for e in result['evidence'])


@pytest.mark.parametrize('kind,operation,code', [('drop', 'RequestStartTransaction', 'message_dropped'),
    ('delay', 'Authorize', 'message_delayed'), ('duplicate', 'PaymentCapture', 'duplicate_receive')])
def test_fault_injection_and_correlation(kind, operation, code):
    s = dataset(injections=[{'kind': kind, 'operation': operation, 'delay_ms': 7000}])['sessions'][0]
    report = correlate(s['events'])
    assert code in {a['code'] for a in report['anomalies']}
    if kind == 'drop':
        assert not any(e['payload'].get('to') == 'charging' for e in s['events'])
    if kind == 'duplicate':
        assert len([e for e in s['events'] if e['event_type'] == 'payment.result']) == 1


def test_chronology_recovers_shuffled_ingestion_and_does_not_merge_sessions():
    s = dataset()['sessions'][0]
    assert correlate(list(reversed(s['events'])))['events'] == s['events']
    another = generate_dataset({'seed': 100, 'scenarios': ['none'], 'per_template': 1, 'split': 'test'})['sessions'][0]
    with pytest.raises(ValueError, match='one session'):
        correlate(s['events'] + another['events'])


def test_missing_response_and_unknown_network_evidence_abstain(conn):
    d = dataset('charger_controller_timeout')
    s = d['sessions'][0]
    s['events'] = [e for e in s['events'] if e['event_type'] != 'controller.watchdog_timeout']
    persist_dataset(conn, d)
    report = correlate(s['events'])
    assert 'missing_response' in {a['code'] for a in report['anomalies']}
    assert MultiComponentAgent(conn).run(s['session_id']).result['root_cause'] is None


def test_missing_communication_records_do_not_prove_a_normal_session(conn):
    d = dataset()
    s = d['sessions'][0]
    s['events'] = [e for e in s['events'] if not e['event_type'].startswith(('message.', 'transport.'))]
    persist_dataset(conn, d)
    assert MultiComponentAgent(conn).run(s['session_id']).result['classification'] == 'inconclusive'


def test_multiple_independent_mechanisms_require_review(conn):
    d = dataset('connector_fault', 'validation', [{'kind': 'duplicate', 'operation': 'MeterValues'}])
    persist_dataset(conn, d)
    result = MultiComponentAgent(conn).run(d['sessions'][0]['session_id']).result
    assert result['classification'] == 'inconclusive'
    assert set(result['candidate_root_causes']) == {'connector_fault', 'network_duplicate'}


@pytest.mark.parametrize('profile,split,injection,causes', [
    ('none', 'test', {'kind': 'delay', 'operation': 'PaymentCapture', 'delay_ms': 8000}, ['network_delay']),
    ('none', 'test', {'kind': 'delay', 'operation': 'PaymentCapture', 'delay_ms': 1}, []),
    ('connector_fault', 'validation', {'kind': 'duplicate', 'operation': 'MeterValues'}, ['connector_fault', 'network_duplicate']),
    ('vehicle_bms_fault', 'test', {'kind': 'drop', 'operation': 'DiscoverChargers'}, ['network_loss']),
])
def test_custom_annotations_record_triggered_causes_not_just_requested_profile(profile, split, injection, causes):
    s = dataset(profile, split, [injection])['sessions'][0]
    assert s['truth']['root_causes'] == causes
    assert s['truth']['root_cause'] == (causes[0] if len(causes) == 1 else None if causes else 'none')
    assert s['truth']['expected_label'] == 'inconclusive'  # Outside standard benchmark.


def test_truth_is_not_a_diagnostic_input(conn):
    d = dataset('vehicle_bms_fault')
    persist_dataset(conn, d)
    sid = d['sessions'][0]['session_id']
    before = MultiComponentAgent(conn).run(sid).result
    conn.execute("UPDATE communication_truth SET annotations_json='{}',template_id='unknown',split='other' WHERE session_id=?", (sid,))
    conn.commit()
    assert MultiComponentAgent(conn).run(sid).result == before


def test_persistence_idempotency_foreign_keys_and_reset_preservation(conn):
    d = dataset()
    assert persist_dataset(conn, d)['inserted'] == 1
    before = event_rows(conn, d['sessions'][0]['session_id'])
    assert persist_dataset(conn, d)['inserted'] == 0
    SyntheticDataset(42, 1).write(conn)
    reset_simulated_rows(conn)
    assert event_rows(conn, d['sessions'][0]['session_id']) == before
    assert conn.execute('SELECT COUNT(*) FROM charging_sessions').fetchone()[0] == 1
    assert not conn.execute('PRAGMA foreign_key_check').fetchall()


def test_feedback_learning_applies_to_correlated_evidence(conn):
    d = dataset('vehicle_bms_fault')
    persist_dataset(conn, d)
    result = diagnose_session(conn, d['sessions'][0]['session_id'])
    res = feedback.create_resolution(conn, result['case_id'], {'reviewer_id': 'rev-test',
        'verified_root_cause': result['category'], 'corrective_action': 'BMS fault confirmed in correlated logs'})
    change = feedback.apply_verified_outcome(conn, res['resolution_id'])
    assert change['applied'] and any(ch['signal_key'] == 'mc_vehicle_bms_fault' for ch in change['changes'])
    assert feedback.apply_verified_outcome(conn, res['resolution_id'])['already_applied']


def test_reviewer_disabled_rule_prevents_automatic_fault_assertion(conn):
    d = dataset('vehicle_bms_fault')
    persist_dataset(conn, d)
    conn.execute("UPDATE knowledge_rules SET active=0 WHERE signal_key='mc_vehicle_bms_fault'")
    conn.commit()
    result = MultiComponentAgent(conn).run(d['sessions'][0]['session_id']).result
    assert result['root_cause'] is None
    assert any('disabled' in q for q in result['unresolved_questions'])


def test_configuration_is_reproducible_and_templates_disjoint():
    d = generate_dataset({'split': 'all', 'per_template': 2})
    assert d == generate_dataset({'split': 'all', 'per_template': 2})
    groups = {split: {t['template_id'] for t in templates() if t['split'] == split} for split in ('train', 'validation', 'test')}
    assert not groups['train'] & groups['test'] and not groups['validation'] & groups['test']
    assert len({s['session_id'] for s in d['sessions']}) == 72


@pytest.mark.parametrize('root', ['stale_availability', 'metering_mismatch'])
def test_component_health_includes_cross_component_inconsistency(root):
    observations = correlate(dataset(root)['sessions'][0]['events'])
    assert next(c for c in observations['components'] if c['component_type'] == 'csms')['health'] == 'degraded'


def test_invalid_event_and_generator_input():
    with pytest.raises(ValueError):
        GenerateRequest(per_template=1000)
    with pytest.raises(ValueError):
        generate_dataset({'scenarios': ['invented_fault']})
    s = dataset()['sessions'][0]
    e = copy.deepcopy(s['events'][0])
    e['timestamp'] = '2026-01-01T00:00:00'
    with pytest.raises(ValueError):
        Event.model_validate(e)
