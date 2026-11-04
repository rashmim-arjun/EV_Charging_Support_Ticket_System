def complaint(client):
    return client.post('/api/v1/cases',json={'app_id':'statiq','complaint_text':'Please review my visit; I do not have complete evidence.'}).json()['case']


def test_administrative_closure_does_not_learn_a_fictional_fault(client):
    full=complaint(client);cid=full['case']['case_id']
    result=client.post(f'/api/v1/cases/{cid}/resolution',json={'reviewer_id':'rev-001','verified_root_cause':'no_fault_established','corrective_action':'Customer confirmed that the visit completed normally.'})
    assert result.status_code==201,result.text
    assert client.post(f'/api/v1/cases/{cid}/learning/preview').json()['changes']==[]
    assert client.post(f'/api/v1/cases/{cid}/learning/apply').json()['changes']==[]
    t=client.get('/api/v1/tickets/'+cid).json()
    assert t['state']=='resolved' and t['decision']['verified_classification']=='no_fault_established'


def test_reopened_ticket_keeps_versioned_diagnosis_resolution_and_learning(client):
    full=complaint(client);cid=full['case']['case_id']
    payload={'reviewer_id':'rev-001','verified_root_cause':'session_fails_to_start','corrective_action':'Reviewer checked initial incident records.'}
    assert client.post(f'/api/v1/cases/{cid}/resolution',json=payload).status_code==201
    first=client.post(f'/api/v1/cases/{cid}/learning/apply').json()
    t=client.get('/api/v1/tickets/'+cid).json()
    opened=client.patch('/api/v1/tickets/'+cid,json={'version':t['version'],'actor':'operator','reason':'Customer supplied new evidence after resolution','state':'investigating'})
    assert opened.status_code==200,opened.text
    investigated=client.post(f'/api/v1/tickets/{cid}/investigate').json()
    assert investigated['diagnosis']['version']==2 and investigated['resolution'] is None
    assert investigated['case']['case_id']==cid and investigated['case']['status']=='awaiting_review'
    resolution=client.post(f'/api/v1/cases/{cid}/resolution',json={**payload,'verified_root_cause':'network_or_connectivity_issue','corrective_action':'Reviewer corrected the category after new evidence.'})
    assert resolution.status_code==201,resolution.text
    second=client.post(f'/api/v1/cases/{cid}/learning/apply').json()
    assert second['resolution_id']!=first['resolution_id']
    assert client.get(f'/api/v1/cases/{cid}/trace?version=1').status_code==200
    assert client.get(f'/api/v1/cases/{cid}/trace?version=2').status_code==200
    latest=client.get('/api/v1/cases/'+cid).json()
    assert latest['resolution']['verified_root_cause']=='network_or_connectivity_issue'
    assert all(e['diagnosis_version']==2 for items in latest['evidence'].values() for e in items)
    assert client.get('/api/v1/cases').json()['total']==1


def test_reported_safety_without_logs_is_urgent_triage_not_component_blame(client):
    response=client.post('/api/v1/cases',json={'app_id':'statiq','complaint_text':'I saw smoke and sparks beside the cable; please investigate urgently.'})
    assert response.status_code==201,response.text
    t=response.json()['case']['ticket']
    assert t['assigned_team']=='triage' and t['priority']=='P0' and t['state']=='escalated'
    assert t['decision']['classification']=='inconclusive'
    assert not t['decision']['originating_component']
