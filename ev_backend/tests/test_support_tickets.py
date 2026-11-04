import json
import sqlite3
import pytest
from app.communication.simulator import generate_dataset
from app.communication.correlation import correlate
from app.communication.storage import persist_dataset
from app.communication.diagnosis import MultiComponentAgent
from app.core.observations import ObservationReader
from app.services.tickets import decide


@pytest.mark.parametrize('root,team,priority',[
    ('vehicle_bms_fault','vehicle_specialists','P1'),('connector_fault','charger_maintenance','P1'),
    ('network_loss','network_operations','P2'),('authorization_conflict','application_support','P2'),
    ('stale_availability','csms_engineering','P2'),('metering_mismatch','csms_engineering','P2'),
    ('payment_conflict','payment_support','P2'),('inconclusive','triage','P2'),('none','triage','P3')])
def test_customer_ticket_uses_component_logs_and_assigns_supported_owner(client,root,team,priority):
    generated = client.post('/api/v1/communication/generate',json={'scenarios':[root],'per_template':1}).json()
    sid = generated['session_ids'][0]
    response = client.post('/api/v1/cases',json={'app_id':'statiq','complaint_text':'I could not understand what happened during my charging visit. Please investigate.',
        'session_ref':sid,'data_origin':'simulated'})
    assert response.status_code == 201,response.text
    full = response.json()['case']
    ticket = full['ticket']
    assert ticket['ticket_id'] == full['case']['case_id']
    assert (ticket['assigned_team'],ticket['priority']) == (team,priority)
    assert ticket['history'][0]['action'] == 'created' and ticket['history'][-1]['action']=='investigated'
    assert ticket['decision']['evidence'] or root=='inconclusive'
    assert ticket['decision']['delivery_scope'].startswith('Local')
    again = client.post(f"/api/v1/tickets/{ticket['ticket_id']}/investigate")
    assert again.status_code==200,again.text
    assert again.json()['diagnosis']['version']==2
    assert client.get('/api/v1/cases').json()['total']==1


def test_uncertainty_does_not_reduce_safety_priority_or_guess_owner(conn):
    data = generate_dataset({'scenarios':['vehicle_bms_fault'],'per_template':1})
    session = data['sessions'][0]
    received = next(e for e in session['events'] if e['event_type']=='message.received')
    received['payload']['operation'] = 'ContradictoryOperation'
    persist_dataset(conn,data)
    result = MultiComponentAgent(conn).run(session['session_id']).result
    decision = decide(result,session['events'],'My charging was interrupted.')
    assert result['classification']=='inconclusive'
    assert decision['assigned_team']=='triage' and decision['priority']=='P1'
    assert 'vehicle_specialists' in decision['supporting_teams']
    assert decision['requires_escalation'] and decision['requires_human_review']
    assert decide(result,session['events'],'I saw smoke at the connector')['priority']=='P0'


def test_human_escalation_resolution_close_and_stale_override(client):
    full = client.post('/api/v1/cases',json={'app_id':'statiq','complaint_text':'Charging did not start and I have no session identifier.'}).json()['case']
    t = full['ticket']; cid=t['case_id']
    body = {'version':t['version'],'actor':'operator-1','reason':'Escalating for manual investigation','state':'escalated','assigned_team':'csms_engineering','priority':'P1'}
    response = client.patch('/api/v1/tickets/'+cid,json=body)
    assert response.status_code==200,response.text
    assert response.json()['manual_assignment'] and response.json()['state']=='escalated'
    assert client.patch('/api/v1/tickets/'+cid,json=body).status_code==409
    latest = response.json()
    assert client.patch('/api/v1/tickets/'+cid,json={**body,'version':latest['version'],'state':'closed'}).status_code==409
    reviewed = client.post(f'/api/v1/cases/{cid}/resolution',json={'reviewer_id':'rev-001','verified_root_cause':'session_fails_to_start','corrective_action':'Reviewed available information and contacted customer.'})
    assert reviewed.status_code==201,reviewed.text
    latest = client.get('/api/v1/tickets/'+cid).json()
    assert latest['state']=='resolved' and latest['resolved_at']
    closed = client.patch('/api/v1/tickets/'+cid,json={**body,'version':latest['version'],'state':'closed'}).json()
    assert closed['state']=='closed' and closed['closed_at']
    assert [h['action'] for h in closed['history']][-2:]==['resolved','human_override']
    assert client.post('/api/v1/tickets/'+cid+'/investigate').status_code==409
    assert client.post(f'/api/v1/cases/{cid}/learning/apply').status_code==200


def test_attempt_ids_separate_successful_retry_from_duplicate_or_conflict(conn):
    data=generate_dataset({'scenarios':['none'],'per_template':1,'injections':[{'kind':'retry','operation':'Authorize','delay_ms':4100}]})
    s=data['sessions'][0]
    assert s['status']=='completed'
    report=correlate(s['events'])
    assert not any('conflict' in a['code'] or a['code']=='duplicate_receive' for a in report['anomalies'])
    attempts=[f for f in report['flows'] if f['operation']=='Authorize']
    assert {f['status'] for f in attempts}=={'dropped','delivered'}
    assert len({f['message_id'] for f in attempts})==1 and len({f['attempt_id'] for f in attempts})==2
    persist_dataset(conn,data)
    assert MultiComponentAgent(conn).run(s['session_id']).result['root_cause']=='network_loss'


def test_runtime_agents_cannot_read_or_write_annotations(conn):
    from app.agent.agent import DiagnosticAgent
    from app.agent.baseline import FixedCheckBaseline
    data=generate_dataset({'scenarios':['network_loss'],'per_template':1})
    persist_dataset(conn,data)
    for agent in (DiagnosticAgent(conn),FixedCheckBaseline(conn),MultiComponentAgent(conn)):
        for sql in ('SELECT * FROM communication_truth','SELECT * FROM communication_runs',
                    'SELECT scenario_id FROM charging_sessions','SELECT ground_truth_category FROM cases',
                    "UPDATE knowledge_rules SET weight=1", "ATTACH DATABASE ':memory:' AS other"):
            with pytest.raises(sqlite3.DatabaseError):
                agent.conn.execute(sql).fetchall()
    sid=data['sessions'][0]['session_id']
    before=MultiComponentAgent(conn).run(sid).result
    conn.execute('DELETE FROM communication_truth');conn.execute("UPDATE communication_runs SET config_json='{}'");conn.commit()
    assert MultiComponentAgent(conn).run(sid).result==before


def test_ticket_migration_preserves_existing_cases(tmp_path):
    from app.core.db import connect,init_db,MIGRATIONS
    c=connect(str(tmp_path/'upgrade.db'))
    c.execute('CREATE TABLE schema_version(version INTEGER PRIMARY KEY,applied_at TEXT)')
    for n,sql in enumerate(MIGRATIONS[:4],1):
        c.executescript(sql);c.execute('INSERT INTO schema_version(version) VALUES (?)',(n,));c.commit()
    c.execute("INSERT INTO apps(app_id,display_name,app_type) VALUES ('statiq','Statiq','charging_network')")
    c.execute("INSERT INTO cases(case_id,app_id,complaint_text_redacted,data_origin,status) VALUES ('old-case','statiq','Existing complaint','simulated','resolved')")
    c.commit();init_db(c);init_db(c)
    assert c.execute("SELECT state FROM support_tickets WHERE case_id='old-case'").fetchone()[0]=='resolved'
    assert c.execute('SELECT count(*) FROM cases').fetchone()[0]==1
    assert not c.execute('PRAGMA foreign_key_check').fetchall()
    c.close()
