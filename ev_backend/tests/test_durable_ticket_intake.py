def test_ticket_can_be_opened_before_investigation(client):
    created=client.post('/api/v1/tickets',json={'app_id':'statiq','complaint_text':'Charging did not start; please investigate my visit.'})
    assert created.status_code==201,created.text
    full=created.json()['case'];cid=full['case']['case_id']
    assert full['ticket']['state']=='new' and full['diagnosis'] is None
    investigated=client.post(f'/api/v1/tickets/{cid}/investigate')
    assert investigated.status_code==200,investigated.text
    assert investigated.json()['case']['case_id']==cid
    assert client.get('/api/v1/cases').json()['total']==1


def test_automatic_investigation_failure_keeps_customer_complaint(client,monkeypatch):
    from app.agent.agent import DiagnosticAgent
    original=DiagnosticAgent.run
    def failure(*args):raise RuntimeError('Forced diagnostic service outage')
    monkeypatch.setattr(DiagnosticAgent,'run',failure)
    response=client.post('/api/v1/cases',json={'app_id':'statiq','complaint_text':'Charging did not start and I need help.'})
    assert response.status_code==503,response.text
    cid=response.json()['error']['details']['ticket_id']
    saved=client.get('/api/v1/cases/'+cid).json()
    assert saved['ticket']['state']=='awaiting_evidence' and saved['diagnosis'] is None
    assert saved['ticket']['history'][-1]['action']=='investigation_failed'
    monkeypatch.setattr(DiagnosticAgent,'run',original)
    assert client.post(f'/api/v1/tickets/{cid}/investigate').status_code==200
    assert client.get('/api/v1/cases').json()['total']==1
