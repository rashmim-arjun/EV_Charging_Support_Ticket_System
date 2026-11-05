"""Realistic demo intake must preserve user data and contain actual diagnoses."""
from datetime import datetime, timedelta, timezone
import json

from app.communication.diagnosis import MultiComponentAgent
from app.communication.storage import event_rows
from app.services import tickets
from app.services.case_service import get_case_full
from app.services.intake import build_complaint
from scripts.seed_demo_tickets import seed_demo_tickets, REVIEWER


def test_demo_tickets_are_complete_recent_and_keep_existing_records(conn):
    original = tickets.open_ticket(conn, build_complaint({
        'app_id':'statiq','complaint_text':'An existing customer complaint that must be preserved.'}))
    before = get_case_full(conn,original)
    rules = [tuple(row) for row in conn.execute('SELECT * FROM knowledge_rules ORDER BY rule_id')]
    now = datetime(2026,11,5,10,0,tzinfo=timezone.utc)
    result = seed_demo_tickets(conn,now=now)
    assert result['added'] == 24
    assert get_case_full(conn,original) == before
    assert [tuple(row) for row in conn.execute('SELECT * FROM knowledge_rules ORDER BY rule_id')] == rules
    assert conn.execute('SELECT COUNT(*) FROM knowledge_changes').fetchone()[0] == 0
    assert conn.execute('SELECT COUNT(*) FROM cases').fetchone()[0] == 25
    assert set(result['states']) == {'new','assigned','investigating','awaiting_evidence','escalated','resolved','closed'}
    priorities = {row['priority'] for row in result['tickets']}
    assert {'P0','P1','P2','P3'} <= priorities
    for item in result['tickets']:
        full = get_case_full(conn,item['ticket_id'])
        assert full['case']['data_origin'] == 'simulated'
        assert full['ticket']['state'] == item['state']
        created = datetime.fromisoformat(full['case']['created_at'])
        assert now-timedelta(days=14) <= created <= now
        events = event_rows(conn,item['session_id'])
        assert events and all(datetime.fromisoformat(e['timestamp']) <= created for e in events)
        assert all(e['session_id'] == item['session_id'] for e in events)
        assert full['complaint']['reported_station_id'].startswith('STN-DEMO-')
        history = full['ticket']['history']
        assert all(created <= datetime.fromisoformat(row['created_at']) <= now for row in history)
        if item['state'] == 'new':
            assert full['diagnosis'] is None
        else:
            assert full['diagnosis'] is not None
            assert full['recommendations']
            evidence_ids = {e['event_id'] for e in events}
            communication = conn.execute('SELECT result_json FROM communication_diagnoses WHERE case_id=?', (item['ticket_id'],)).fetchone()
            outcome = json.loads(communication[0])
            assert all(set(e['event_ids']) <= evidence_ids for e in outcome['evidence'])
        if item['state'] in ('closed','resolved'):
            assert full['resolution']['reviewer_id'] == REVIEWER
            assert full['resolution']['corrective_action'].startswith('[SIMULATED OUTCOME]')
            assert full['resolution']['learning_applied'] == 0
            assert datetime.fromisoformat(full['resolution']['resolved_at']) >= created
    assert conn.execute('SELECT active FROM reviewers WHERE reviewer_id=?',(REVIEWER,)).fetchone()[0] == 0
    assert not conn.execute('PRAGMA foreign_key_check').fetchall()


def test_repeating_demo_seed_does_not_duplicate_or_overwrite_operator_changes(conn):
    now = datetime(2026,11,5,10,0,tzinfo=timezone.utc)
    first = seed_demo_tickets(conn,now=now)
    cid = first['tickets'][0]['ticket_id']
    conn.execute('UPDATE cases SET complaint_text_redacted=? WHERE case_id=?', ('Operator added customer follow-up details.',cid))
    conn.commit()
    tables = ('cases','support_tickets','ticket_history','communication_sessions','communication_events','diagnoses','resolutions')
    before = {table:[tuple(row) for row in conn.execute(f'SELECT * FROM {table}')] for table in tables}
    result = seed_demo_tickets(conn,now=now+timedelta(days=1))
    assert result['added'] == 0 and result['skipped'] == 24
    assert {table:[tuple(row) for row in conn.execute(f'SELECT * FROM {table}')] for table in tables} == before


def test_recentering_session_clocks_preserves_fault_detection(conn):
    result = seed_demo_tickets(conn,now=datetime(2026,11,5,10,0,tzinfo=timezone.utc))
    outcomes = [MultiComponentAgent(conn).run(item['session_id']).result for item in result['tickets']]
    causes = {outcome['root_cause'] for outcome in outcomes}
    assert {'none','network_loss','vehicle_bms_fault','connector_fault','payment_conflict',None} <= causes
    for outcome in outcomes:
        if outcome['root_cause'] == 'none':
            assert outcome['classification'] == 'normal'
        if outcome['classification'] == 'inconclusive':
            assert outcome['root_cause'] is None
