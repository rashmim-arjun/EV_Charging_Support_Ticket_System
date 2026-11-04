"""Exercise actual API contracts and failures with an isolated database."""
import json
import os
from concurrent.futures import ThreadPoolExecutor
import pytest
from app.core import db
from app.data.synthetic_generator import SyntheticDataset


def seed():
    conn = db.connect()
    ds = SyntheticDataset(42, 2)
    ds.write(conn)
    conn.close()
    return ds


def new_case(client):
    ds = seed()
    response = client.post('/api/v1/cases', json=ds.complaints()[0]['payload'])
    assert response.status_code == 201, response.text
    return response.json()['case_summary']['case_id']


@pytest.mark.parametrize('path', ['/health', '/apps', '/categories', '/reviewers', '/cases',
    '/knowledge/rules', '/knowledge/tool-priors', '/knowledge/changes', '/metrics/performance',
    '/metrics/recurring', '/reviews', '/evaluation/summary'])
def test_all_read_endpoints_have_valid_contracts(client, path):
    r = client.get('/api/v1' + path)
    assert r.status_code == 200, r.text
    assert r.json() is not None


def test_complete_feedback_learning_and_metrics_workflow(client):
    cid = new_case(client)
    full = client.get(f'/api/v1/cases/{cid}').json()
    assert full['diagnosis']['primary_category'] == 'session_fails_to_start'
    assert full['diagnosis']['confidence'] is not None
    assert full['diagnosis']['supporting_evidence_ids']
    assert client.get(f'/api/v1/cases/{cid}/trace').json()['steps']
    r = client.post(f'/api/v1/cases/{cid}/resolution', json={'reviewer_id': 'rev-001',
        'verified_root_cause': 'session_fails_to_start', 'corrective_action': 'Technician verified start timeout'})
    assert r.status_code == 201, r.text
    preview = client.post(f'/api/v1/cases/{cid}/learning/preview').json()
    assert preview['changes'] and preview['dry_run']
    assert client.post(f'/api/v1/cases/{cid}/learning/apply').json()['applied']
    assert client.post(f'/api/v1/cases/{cid}/learning/apply').json()['already_applied']
    changes = client.get('/api/v1/knowledge/changes').json()
    assert changes
    assert client.post(f"/api/v1/knowledge/changes/{changes[0]['change_id']}/revert").status_code == 200
    perf = client.get('/api/v1/metrics/performance').json()
    assert perf['total_resolved_cases'] == 1
    assert perf['primary_accuracy_pct'] == 100
    listing = client.get('/api/v1/cases', params={'status': 'resolved', 'category': 'session_fails_to_start', 'page_size': 1}).json()
    assert listing['total'] == 1 and listing['items'][0]['case_id'] == cid


def test_invalid_requests_return_structured_errors(client):
    for path in ['/api/v1/cases/missing', '/api/v1/cases/missing/trace']:
        assert client.get(path).status_code == 404
    r = client.post('/api/v1/cases', json={'app_id': 'unknown', 'complaint_text': 'Charging failed repeatedly'})
    assert r.status_code == 400 and r.json()['error']['code'] == 'invalid_app_id'
    assert client.post('/api/v1/cases', json={'app_id': 'statiq', 'complaint_text': 'short'}).status_code == 422
    assert client.get('/api/v1/cases?page=0').status_code == 422
    assert client.get('/api/v1/reviews?limit=-1').status_code == 422
    assert client.post('/api/v1/knowledge/changes/999/revert').status_code == 404


def test_resolution_validation_duplicate_and_inactive_reviewer(client):
    cid = new_case(client)
    body = {'reviewer_id': 'rev-003', 'verified_root_cause': 'session_fails_to_start', 'corrective_action': 'Verified timeout'}
    assert client.post(f'/api/v1/cases/{cid}/resolution', json=body).status_code == 403
    body['reviewer_id'] = 'rev-001'
    body['verified_root_cause'] = 'unknown'
    assert client.post(f'/api/v1/cases/{cid}/resolution', json=body).status_code == 422
    body['verified_root_cause'] = 'session_fails_to_start'
    assert client.post(f'/api/v1/cases/{cid}/resolution', json=body).status_code == 201
    assert client.post(f'/api/v1/cases/{cid}/resolution', json=body).status_code == 409


@pytest.mark.parametrize('filename,content', [
    ('reviews.csv', 'app_id,text,data_origin\nstatiq,Call 9812345678 about charging failure,manual_test\n'),
    ('reviews.json', json.dumps([{'app_id': 'statiq', 'text': 'Email sample@example.com about failed charging', 'data_origin': 'manual_test'}])),
    ('reviews.csv', 'text,data_origin\nCall 9812345678 about charging failure,manual_test\n'),
    ('reviews.json', json.dumps([{'text': 'Email sample@example.com about failed charging', 'data_origin': 'manual_test'}])),
])
def test_review_import_redacts_storage_and_response(client, filename, content):
    r = client.post('/api/v1/reviews/import', files={'file': (filename, content.encode(), 'text/plain')})
    assert r.status_code == 200 and r.json()['imported'] == 1, r.text
    text = str(client.get('/api/v1/reviews').json())
    assert '9812345678' not in text and 'sample@example.com' not in text
    expected_app = 'statiq' if 'app_id' in content else 'ev_support'
    assert client.get('/api/v1/reviews').json()[0]['app_id'] == expected_app
    conn = db.connect()
    stored = conn.execute('SELECT original_text,redacted_text FROM reviews').fetchone()
    assert stored[0] == stored[1]
    conn.close()


@pytest.mark.parametrize('filename,content', [('bad.json', '{'), ('bad.json', '{}'), ('bad.csv', 'app_id,text\nstatiq,test\n'), ('bad.csv', b'\xff\xff')])
def test_malformed_import_does_not_save_rows(client, filename, content):
    r = client.post('/api/v1/reviews/import', files={'file': (filename, content)})
    assert r.status_code == 400
    assert client.get('/api/v1/reviews').json() == []


def test_import_database_failure_rolls_back_all_rows(client):
    conn = db.connect()
    conn.execute("CREATE TRIGGER fail_second_review BEFORE INSERT ON reviews WHEN NEW.source='FAIL' BEGIN SELECT RAISE(ABORT,'test failure'); END")
    conn.commit()
    conn.close()
    data = [{'app_id': 'statiq', 'text': 'First review must rollback', 'data_origin': 'manual_test'},
            {'app_id': 'statiq', 'text': 'Second review causes failure', 'source': 'FAIL', 'data_origin': 'manual_test'}]
    r = client.post('/api/v1/reviews/import', files={'file': ('data.json', json.dumps(data))})
    assert r.status_code == 400
    assert client.get('/api/v1/reviews').json() == []


def test_review_import_size_limit_and_invalid_rows(client):
    assert client.post('/api/v1/reviews/import', files={'file': ('too-big.csv', b'x' * (2 * 1024 * 1024 + 1))}).status_code == 400
    rows = [{'app_id': 'statiq', 'text': 'Charging review with valid origin', 'data_origin': 'manual_test'},
            {'app_id': 'unknown', 'text': 'Unknown app', 'data_origin': 'manual_test'}, 1]
    r = client.post('/api/v1/reviews/import', files={'file': ('mixed.json', json.dumps(rows))})
    assert r.status_code == 200
    assert r.json()['imported'] == 1 and r.json()['skipped'] == 2


def test_rule_activation_endpoint_and_rollback(client):
    assert client.post('/api/v1/knowledge/rules/1/activation', json={'active': False, 'reason': 'Reviewer deactivates'}).json()['changed']
    changes = client.get('/api/v1/knowledge/changes').json()
    assert client.post(f"/api/v1/knowledge/changes/{changes[0]['change_id']}/revert").status_code == 200
    assert client.get('/api/v1/knowledge/rules').json()[0]['active']


def test_evaluation_endpoint_returns_live_metrics_and_confusion_matrix(client, monkeypatch, tmp_path):
    from app.evaluation import evaluation
    monkeypatch.setattr(evaluation, 'REPORT_DIR', str(tmp_path / 'reports'))
    r = client.post('/api/v1/evaluation/run', json={'seed': 7, 'cases_per_category': 1})
    assert r.status_code == 200, r.text
    assert r.json()['dataset_size'] == 25
    for method in r.json()['metrics'].values():
        assert sum(map(sum, method['confusion_matrix']['rows'])) == 25
        assert method['traceability_pct'] == 100
    assert client.get('/api/v1/evaluation/summary').json()['available']
    assert client.get('/api/v1/evaluation/results').json()['per_case']
    assert client.post('/api/v1/evaluation/run', json={'cases_per_category': 0}).status_code == 422
