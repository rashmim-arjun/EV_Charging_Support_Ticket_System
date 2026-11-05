"""Safety and no-fault outcomes must remain coherent across the public views."""
import json
import pytest
from app.core import db
from app.services.recommendations import NO_FAULT_ACTION


@pytest.mark.parametrize('phrase', ['burning smell', 'burnt smell', 'smell of burning'])
@pytest.mark.parametrize('endpoint', ['/api/v1/cases', '/api/v1/tickets'])
def test_reported_burning_requires_urgent_review_without_inventing_a_cause(client, phrase, endpoint):
    response = client.post(endpoint,json={'complaint_text':f'There is a {phrase} near the charging cable. Please review urgently.'})
    assert response.status_code == 201,response.text
    full = response.json()['case']
    assert full['ticket']['priority'] == 'P0'
    assert full['ticket']['state'] == 'escalated'
    assert full['ticket']['assigned_team'] == 'triage'
    assert not full['ticket']['decision']['evidence']
    if full['diagnosis']:
        assert full['diagnosis']['outcome'] == 'inconclusive'
        assert full['diagnosis']['primary_category'] is None


def healthy_ticket(client, complaint='Charging completed; please check my receipt and session records.'):
    generated = client.post('/api/v1/communication/generate',json={'seed':625,'per_template':1,'scenarios':['none']})
    sid = generated.json()['session_ids'][0]
    response = client.post('/api/v1/cases',json={'complaint_text':complaint,'session_ref':sid,'data_origin':'simulated'})
    assert response.status_code == 201,response.text
    return response.json()['case']


def test_no_fault_agrees_in_detail_queue_and_correlated_result(client):
    full = healthy_ticket(client)
    cid = full['case']['case_id']
    assert full['diagnosis']['outcome'] == 'no_fault_established'
    assert full['diagnosis']['root_cause'] == 'none'
    assert 'completion' in full['diagnosis']['evidence_strength_label']
    assert full['recommendations'][0]['action'] == NO_FAULT_ACTION
    assert full['evidence']['neutral']
    detail = client.get('/api/v1/cases/'+cid).json()
    listed = client.get('/api/v1/cases').json()['items'][0]
    communication = client.get('/api/v1/communication/sessions/'+full['complaint']['reported_session_ref']).json()
    assert detail['diagnosis']['outcome'] == listed['diagnosis']['outcome'] == 'no_fault_established'
    assert communication['diagnosis']['classification'] == 'normal'


def test_historic_healthy_result_is_presented_correctly_without_rewriting_its_grade(client):
    full = healthy_ticket(client)
    cid = full['case']['case_id']
    conn = db.connect()
    try:
        before = tuple(conn.execute('SELECT * FROM diagnoses WHERE case_id=?',(cid,)).fetchone())
        row = conn.execute('SELECT id,result_json FROM communication_diagnoses WHERE case_id=?',(cid,)).fetchone()
        old = json.loads(row['result_json']);old.pop('diagnosis_id')
        conn.execute('UPDATE communication_diagnoses SET result_json=? WHERE id=?',(json.dumps(old),row['id']))
        conn.execute("UPDATE recommendations SET action='Request missing session logs' WHERE case_id=?",(cid,))
        conn.commit()
        detail = client.get('/api/v1/cases/'+cid).json()
        assert detail['diagnosis']['outcome'] == 'no_fault_established'
        assert not detail['recommendations']  # Obsolete missing-log advice is not current advice.
        assert tuple(conn.execute('SELECT * FROM diagnoses WHERE case_id=?',(cid,)).fetchone()) == before
    finally:
        conn.close()


def test_unverifiable_completion_is_not_presented_as_no_fault(client):
    full = healthy_ticket(client)
    cid = full['case']['case_id']
    conn = db.connect()
    try:
        row = conn.execute('SELECT id,result_json FROM communication_diagnoses WHERE case_id=?',(cid,)).fetchone()
        data=json.loads(row['result_json'])
        data['evidence'][0]['event_ids']=['not-in-this-session']
        conn.execute('UPDATE communication_diagnoses SET result_json=? WHERE id=?',(json.dumps(data),row['id']))
        conn.commit()
    finally:
        conn.close()
    detail=client.get('/api/v1/cases/'+cid).json()
    assert detail['diagnosis']['outcome']=='inconclusive'
    assert all(r['action'] != NO_FAULT_ACTION for r in detail['recommendations'])


def test_normal_completion_does_not_clear_a_customer_reported_hazard(client):
    full=healthy_ticket(client,'Charging finished, but there was a burning smell near the cable. Please investigate.')
    assert full['ticket']['priority']=='P0'
    assert full['diagnosis']['outcome']=='inconclusive'
    assert full['ticket']['decision']['requires_human_review']
    assert 'immediate human safety review' in full['recommendations'][0]['action']
