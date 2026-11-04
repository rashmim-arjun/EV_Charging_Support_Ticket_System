"""New regressions for evidence integrity, lifecycle consistency and escalation audit."""
from app.services.tickets import decide, investigation_failed


def _ticket(client, scenario='network_loss'):
    generated=client.post('/api/v1/communication/generate',json={'scenarios':[scenario],'per_template':1})
    assert generated.status_code == 201, generated.text
    sid=generated.json()['session_ids'][0]
    response=client.post('/api/v1/cases',json={'app_id':'statiq',
        'complaint_text':'Please check the session; I cannot explain what happened.',
        'session_ref':sid,'data_origin':'simulated'})
    assert response.status_code == 201,response.text
    return response.json()['case']['ticket'],sid


def test_forged_and_missing_event_references_do_not_justify_routing():
    claim={'classification':'probable','root_cause':'payment_conflict','category':'payment_or_billing_failure',
           'component_type':'payment'}
    events=[{'event_id':'REAL-1','event_type':'message.sent','component_type':'app',
             'severity':'info','payload':{},'status':'sent','timestamp':'2026-01-01T00:00:00Z'}]
    for refs in (['FORGED'],['REAL-1','FORGED']):
        decision=decide({**claim,'evidence':[{'root_cause':'payment_conflict','component_type':'payment',
            'event_ids':refs}]},events,'I think it was billing.')
        assert decision['assigned_team']=='triage'
        assert decision['classification']=='inconclusive'
        assert decision['originating_component'] is None
    decision=decide({'classification':'normal','root_cause':'none', 'evidence':[]},events,'all fine')
    assert decision['classification']=='inconclusive' and decision['priority']=='P2'


def test_manual_edits_keep_decision_in_sync_and_unchanged_fields_do_not_set_overrides(client):
    ticket,_=_ticket(client)
    cid=ticket['ticket_id']
    response=client.patch('/api/v1/tickets/'+cid,json={'version':ticket['version'],
        'actor':'operator-1','reason':'Requesting more evidence','state':'awaiting_evidence',
        'assigned_team':ticket['assigned_team'],'priority':ticket['priority'],
        'supporting_teams':ticket['supporting_teams']})
    assert response.status_code == 200,response.text
    updated=response.json()
    assert not updated['manual_assignment'] and not updated['manual_priority']
    response=client.patch('/api/v1/tickets/'+cid,json={'version':updated['version'],
        'actor':'operator-1','reason':'Escalate with additional team','state':'escalated',
        'assigned_team':'csms_engineering','priority':'P1'})
    assert response.status_code == 200,response.text
    after=response.json()
    assert after['decision']['assigned_team']==after['assigned_team']=='csms_engineering'
    assert after['decision']['priority']==after['priority']=='P1'
    assert after['decision']['requires_escalation'] and after['manual_assignment'] and after['manual_priority']
    assert any(h['action']=='escalated' and h['actor']=='operator-1' and h['after']['assigned_team']=='csms_engineering' for h in after['history'])
    assert after['history'][-1]['action']=='human_override'
    reinvestigate=client.post('/api/v1/tickets/'+cid+'/investigate')
    assert reinvestigate.status_code==200,reinvestigate.text
    after=reinvestigate.json()['ticket']
    assert after['state']=='escalated' and after['decision']['assigned_team']=='csms_engineering'


def test_failed_investigation_keeps_urgent_ticket_in_escalation_queue(client,monkeypatch):
    ticket,_=_ticket(client,'connector_fault')
    assert ticket['priority']=='P1' and ticket['state']=='escalated'
    # Exercise the failure state handler on this isolated test database.
    from app.core.db import connect,get_db_path
    with connect(get_db_path()) as conn:
        investigation_failed(conn,ticket['ticket_id'])
    after=client.get('/api/v1/tickets/'+ticket['ticket_id']).json()
    assert after['state']=='escalated'
    assert after['decision']['investigation_status']=='failed'


def test_close_requires_resolution_for_current_diagnosis_version(client):
    ticket,_=_ticket(client)
    cid=ticket['ticket_id']
    response=client.post(f'/api/v1/cases/{cid}/resolution',json={'reviewer_id':'rev-001',
        'verified_root_cause':'network_or_connectivity_issue','corrective_action':'Verified the network logs and restored service.'})
    assert response.status_code==201,response.text
    ticket=client.get('/api/v1/tickets/'+cid).json()
    reopened=client.patch('/api/v1/tickets/'+cid,json={'version':ticket['version'],
        'actor':'operator-2','reason':'Customer reported repeat failure','state':'investigating'})
    assert reopened.status_code==200,reopened.text
    assert client.get('/api/v1/cases/'+cid).json()['case']['status'] != 'resolved'
    assert client.post('/api/v1/tickets/'+cid+'/investigate').status_code==200
    ticket=client.get('/api/v1/tickets/'+cid).json()
    closing=client.patch('/api/v1/tickets/'+cid,json={'version':ticket['version'],
        'actor':'operator-2','reason':'Need a new reviewer verification','state':'resolved'})
    assert closing.status_code==409 and closing.json()['error']['code']=='resolution_required'
