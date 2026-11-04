"""Intake can be submitted without making customers select a provider."""
from datetime import datetime, timezone
import pytest


@pytest.mark.parametrize('endpoint', ['/api/v1/cases','/api/v1/tickets'])
def test_complaint_only_intake_uses_general_support_and_current_time(client, endpoint):
    before = datetime.now(timezone.utc)
    response = client.post(endpoint,json={'complaint_text':'My vehicle would not start charging at the station.'})
    assert response.status_code == 201,response.text
    full = response.json()['case']
    assert full['case']['app_id'] == 'ev_support'
    assert before <= datetime.fromisoformat(full['complaint']['complaint_ts']) <= datetime.now(timezone.utc)
    assert full['complaint']['reported_station_id'] is None
    assert client.get('/api/v1/cases/'+full['case']['case_id']).status_code == 200


@pytest.mark.parametrize('endpoint', ['/api/v1/cases','/api/v1/tickets'])
def test_session_fills_provider_and_station_without_overwriting_reported_time(client, endpoint):
    import os
    from app.core.db import connect
    from app.data.synthetic_generator import SyntheticDataset
    conn = connect(os.environ['EV_DB_PATH'])
    try:
        ds = SyntheticDataset(seed=42,n_per_template=1)
        ds.write(conn)
        session = ds.sessions[0]
    finally:
        conn.close()
    timestamp = '2026-11-01T10:30:00+05:30'
    response = client.post(endpoint,json={'complaint_text':'My vehicle would not start charging at the station.',
        'session_ref':session['session_id'],'complaint_ts':timestamp})
    assert response.status_code == 201,response.text
    full = response.json()['case']
    assert full['case']['app_id'] == session['app_id']
    assert full['complaint']['reported_station_id'] == session['station_id']
    assert full['complaint']['complaint_ts'] == timestamp
    context = client.get('/api/v1/tickets/intake-context',params={'session_ref':session['session_id']}).json()
    assert context['session']['station_id'] == session['station_id']
    assert context['location_available'] is False
    assert context['stations']
    assert 'user_ref' not in context['session']


def test_unknown_reference_never_invents_station_or_provider(client):
    context = client.get('/api/v1/tickets/intake-context',params={'session_ref':'unknown'}).json()
    assert context == {'session':None,'stations':[],'location_available':False}
    response = client.post('/api/v1/tickets',json={'complaint_text':'Charging would not start. Please help.',
        'session_ref':'unknown','station_id':'CUSTOM-STATION'})
    assert response.status_code == 201,response.text
    full = response.json()['case']
    assert full['case']['app_id'] == 'ev_support'
    assert full['complaint']['reported_station_id'] == 'CUSTOM-STATION'
