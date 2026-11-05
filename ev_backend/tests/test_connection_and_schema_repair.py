"""Regression coverage for the shipped v5 DB and local API connection."""
import sqlite3

import pytest
from fastapi.testclient import TestClient

from app.core import db
from app.main import create_app
from app.services.diagnosis import diagnose_and_persist
from app.services.intake import build_complaint


def test_shipped_v5_schema_drift_preserves_records_and_restores_diagnosis(conn):
    complaint = build_complaint({'app_id': 'statiq', 'complaint_text': 'Charging never started; please investigate.'})
    cid = diagnose_and_persist(conn, complaint)['case_id']
    before = {t: [tuple(r) for r in conn.execute(f'SELECT * FROM {t}')]
              for t in ('cases', 'diagnoses', 'support_tickets', 'ticket_history')}
    # Reproduce the actual shipped file: v5 marker and ticket tables, but no
    # version columns and the old one-resolution-per-case index.
    conn.execute('DROP TRIGGER create_ticket_payment')
    conn.execute('DROP TABLE ticket_payments')
    conn.execute('DROP TABLE payment_submissions')
    conn.execute('DELETE FROM schema_version WHERE version>=6')
    conn.execute('DROP INDEX idx_resolution_case_version')
    for table in ('case_checks', 'case_evidence', 'resolutions'):
        conn.execute(f'ALTER TABLE {table} DROP COLUMN diagnosis_version')
    conn.execute('CREATE UNIQUE INDEX idx_resolution_case ON resolutions(case_id)')
    conn.commit()
    with pytest.raises(sqlite3.OperationalError, match='diagnosis_version'):
        diagnose_and_persist(conn, complaint, case_id=cid)
    db.init_db(conn)
    db.init_db(conn)
    assert conn.execute('SELECT MAX(version) FROM schema_version').fetchone()[0] == db.SCHEMA_VERSION_KEY
    for table, rows in before.items():
        assert rows == [tuple(r) for r in conn.execute(f'SELECT * FROM {table}')]
    assert diagnose_and_persist(conn, complaint, case_id=cid)['case_id'] == cid
    assert conn.execute('SELECT MAX(version) FROM diagnoses WHERE case_id=?', (cid,)).fetchone()[0] == 2
    assert not conn.execute('PRAGMA foreign_key_check').fetchall()


def test_failed_migration_rolls_back_ddl_and_version_marker(conn, monkeypatch):
    monkeypatch.setattr(db, 'MIGRATIONS', [*db.MIGRATIONS,
        'ALTER TABLE cases ADD COLUMN should_rollback TEXT; INSERT INTO missing_table VALUES (1);'])
    with pytest.raises(sqlite3.OperationalError):
        db.init_db(conn)
    assert 'should_rollback' not in {r['name'] for r in conn.execute('PRAGMA table_info(cases)')}
    assert conn.execute('SELECT MAX(version) FROM schema_version').fetchone()[0] == db.SCHEMA_VERSION_KEY
    assert not conn.in_transaction


@pytest.mark.parametrize('origin', ['http://localhost:5173', 'http://127.0.0.1:5173'])
def test_local_cors_preflight_and_post(client, origin):
    response = client.options('/api/v1/cases', headers={
        'Origin': origin, 'Access-Control-Request-Method': 'POST',
        'Access-Control-Request-Headers': 'content-type'})
    assert response.status_code == 200
    assert response.headers['access-control-allow-origin'] == origin
    response = client.post('/api/v1/cases', headers={'Origin': origin}, json={
        'app_id': 'statiq', 'complaint_text': 'Charging did not start. Please help.'})
    assert response.status_code == 201, response.text
    assert response.headers['access-control-allow-origin'] == origin


def test_custom_cors_origin_from_environment(tmp_path, monkeypatch):
    monkeypatch.setenv('EV_DB_PATH', str(tmp_path / 'custom-origin.db'))
    monkeypatch.setenv('EV_CORS_ORIGINS', ' http://localhost:5174/ , http://127.0.0.1:5174 ')
    with TestClient(create_app()) as client:
        response = client.get('/api/v1/health', headers={'Origin': 'http://127.0.0.1:5174'})
        assert response.headers['access-control-allow-origin'] == 'http://127.0.0.1:5174'
        response = client.options('/api/v1/cases', headers={
            'Origin': 'https://untrusted.example', 'Access-Control-Request-Method': 'POST'})
        assert response.status_code == 400


def test_unhandled_errors_remain_readable_by_direct_browser_clients(tmp_path, monkeypatch):
    from app.services import case_service
    monkeypatch.setenv('EV_DB_PATH', str(tmp_path / 'errors.db'))
    def fail(*args, **kwargs):
        raise RuntimeError('Forced internal failure')
    monkeypatch.setattr(case_service, 'list_cases', fail)
    with TestClient(create_app(), raise_server_exceptions=False) as client:
        response = client.get('/api/v1/cases', headers={'Origin': 'http://localhost:5173'})
        assert response.status_code == 500
        assert response.json()['error']['code'] == 'internal_error'
        assert response.headers['access-control-allow-origin'] == 'http://localhost:5173'


def test_no_api_keys_or_logs_still_produces_honest_diagnosis(client, monkeypatch):
    for name in ('OPENAI_API_KEY', 'GEMINI_API_KEY', 'ANTHROPIC_API_KEY'):
        monkeypatch.delenv(name, raising=False)
    response = client.post('/api/v1/cases', json={
        'app_id': 'statiq', 'complaint_text': 'Charging did not start and I need help.',
        'session_ref': 'nonexistent-session'})
    assert response.status_code == 201, response.text
    full = response.json()['case']
    diagnosis = full['diagnosis']
    assert diagnosis['classification'] in ('inconclusive', 'requires_further_investigation')
    assert diagnosis['primary_category'] is None
    assert diagnosis['unresolved_questions']
    cid = full['case']['case_id']
    assert client.get('/api/v1/cases/' + cid).json()['diagnosis'] == diagnosis
    assert client.get('/api/v1/cases/' + cid + '/trace').status_code == 200
    assert client.post('/api/v1/tickets/' + cid + '/investigate').json()['diagnosis']['version'] == 2


def test_service_exception_is_logged_and_retryable(client, monkeypatch):
    from app.agent.agent import DiagnosticAgent
    from app.routers import errors
    from unittest.mock import Mock
    logger = Mock()
    monkeypatch.setattr(errors, 'get_logger', lambda _: logger)
    def fail(*args):
        raise sqlite3.OperationalError('database is locked')
    monkeypatch.setattr(DiagnosticAgent, 'run', fail)
    response = client.post('/api/v1/cases', json={
        'app_id': 'statiq', 'complaint_text': 'Charging did not start and I need help.'})
    assert response.status_code == 503
    error = response.json()['error']
    assert error['details']['reason'] == 'database_busy'
    assert 'retry' in error['message'].lower()
    assert logger.error.called
    cid = error['details']['ticket_id']
    assert client.get('/api/v1/cases/' + cid).status_code == 200
    response = client.post('/api/v1/tickets/' + cid + '/investigate')
    assert response.status_code == 503
    assert response.json()['error']['details']['ticket_id'] == cid
