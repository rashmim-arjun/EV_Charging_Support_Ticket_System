import json
import pytest
from app.core import db
from app.communication.evaluation import evaluate_communication


def test_monitoring_api_generation_and_truth_separation(client):
    response = client.post('/api/v1/communication/generate', json={'seed': 99, 'per_template': 1, 'split': 'test', 'scenarios': ['network_loss']})
    assert response.status_code == 201, response.text
    sid = response.json()['session_ids'][0]
    assert response.json()['inserted'] == 1
    listing = client.get('/api/v1/communication/sessions').json()
    assert listing['total'] == 1 and listing['items'][0]['event_count'] > 1
    detail = client.get('/api/v1/communication/sessions/' + sid).json()
    assert 'truth' not in detail and 'annotations_json' not in json.dumps(detail)
    assert detail['anomalies'] and detail['flows']
    diagnosed = client.post(f'/api/v1/communication/sessions/{sid}/diagnose')
    assert diagnosed.status_code == 200, diagnosed.text
    result = diagnosed.json()
    assert result['root_cause'] == 'network_loss' and result['component_type'] == 'network'
    assert result['case_id']
    assert client.get(f"/api/v1/cases/{result['case_id']}").status_code == 200
    assert client.get('/api/v1/communication/sessions/' + sid).json()['diagnosis']['case_id'] == result['case_id']


@pytest.mark.parametrize('path', ['/api/v1/communication/sessions/missing', '/api/v1/communication/sessions?page=0'])
def test_monitoring_bad_requests_are_explicit(client, path):
    assert client.get(path).status_code in (404, 422)


def test_generation_validation_and_idempotency(client):
    cfg = {'seed': 2, 'per_template': 1, 'scenarios': ['none']}
    first = client.post('/api/v1/communication/generate', json=cfg).json()
    assert client.post('/api/v1/communication/generate', json=cfg).json()['inserted'] == 0
    assert client.post('/api/v1/communication/generate', json={'per_template': 0}).status_code == 422
    assert client.post('/api/v1/communication/generate', json={'scenarios': ['bad']}).status_code == 422
    result = client.post(f"/api/v1/communication/sessions/{first['session_ids'][0]}/diagnose").json()
    assert result['classification'] == 'normal' and result['root_cause'] == 'none' and result['case_id'] is None


def test_diagnosis_and_legacy_case_commit_atomically(conn, monkeypatch):
    from app.communication.simulator import generate_dataset
    from app.communication.storage import persist_dataset
    from app.communication.service import diagnose_session
    d = generate_dataset({'per_template': 1, 'scenarios': ['vehicle_bms_fault'], 'split': 'test'})
    persist_dataset(conn, d)
    conn.execute("CREATE TRIGGER fail_comm_diagnosis BEFORE INSERT ON communication_diagnoses BEGIN SELECT RAISE(ABORT,'test'); END")
    conn.commit()
    with pytest.raises(Exception):
        diagnose_session(conn, d['sessions'][0]['session_id'])
    assert conn.execute('SELECT COUNT(*) FROM cases').fetchone()[0] == 0
    assert conn.execute('SELECT COUNT(*) FROM diagnoses').fetchone()[0] == 0


def test_inconclusive_observations_do_not_expose_hidden_physical_completion(client):
    result = client.post('/api/v1/communication/generate', json={'per_template': 1, 'scenarios': ['inconclusive']}).json()
    sid = result['session_ids'][0]
    detail = client.get('/api/v1/communication/sessions/' + sid).json()
    assert detail['session']['status'] == 'unknown'
    assert not any(e['event_type'] == 'session.state_changed' for e in detail['events'])
    diagnosis = client.post(f'/api/v1/communication/sessions/{sid}/diagnose').json()
    assert diagnosis['classification'] == 'inconclusive' and diagnosis['confidence'] is None


def test_communication_evaluation_template_holdout_and_reproducibility():
    a = evaluate_communication(7, 1)
    b = evaluate_communication(7, 1)
    assert a['metrics'] == b['metrics']
    assert a['split_sizes'] == {'train': 12, 'validation': 12, 'test': 12}
    for x, y in [('train', 'test'), ('validation', 'test'), ('train', 'validation')]:
        assert not set(a['split_templates'][x]) & set(a['split_templates'][y])
        assert not set(a['split_configuration_hashes'][x]) & set(a['split_configuration_hashes'][y])
    assert a['training']['test_labels_used'] is False
    assert a['training']['knowledge_changes'] > 0
    for method, m in a['metrics'].items():
        assert m['sessions'] == 12
        assert sum(sum(row) for row in m['confusion_matrix']['rows']) == 12
        assert 0 <= m['root_cause_accuracy_pct'] <= 100
        assert m['tool_errors'] == 0


def test_communication_evaluation_endpoint(client, monkeypatch, tmp_path):
    monkeypatch.setenv('EV_REPORT_DIR', str(tmp_path))
    assert not client.get('/api/v1/communication/evaluation').json()['available']
    response = client.post('/api/v1/communication/evaluation', json={'seed': 7, 'per_template': 1})
    assert response.status_code == 200, response.text
    assert set(response.json()['metrics']) == {'fixed_baseline', 'current_adaptive', 'multi_component'}
    assert client.get('/api/v1/communication/evaluation').json()['available']
    assert (tmp_path / 'communication_evaluation.json').exists()
