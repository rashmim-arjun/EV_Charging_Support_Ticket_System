"""Public monitoring/diagnosis orchestration, isolated from benchmark annotations."""
import json
from app.communication.correlation import correlate
from app.communication.diagnosis import MultiComponentAgent
from app.communication.storage import event_rows, get_session
from app.services.diagnosis import diagnose_and_persist


def session_detail(conn, session_id):
    session = get_session(conn, session_id)
    observations = correlate(event_rows(conn, session_id))
    last = conn.execute('SELECT result_json,case_id FROM communication_diagnoses WHERE session_id=? ORDER BY id DESC LIMIT 1', (session_id,)).fetchone()
    return {'session': session, **observations, 'diagnosis': json.loads(last['result_json']) if last else None}


def diagnose_session(conn, session_id, complaint=None, case_id=None):
    if complaint is None and case_id is None:
        previous = conn.execute('SELECT case_id FROM communication_diagnoses WHERE session_id=? AND case_id IS NOT NULL ORDER BY id DESC LIMIT 1',(session_id,)).fetchone()
        if previous:
            from app.services.tickets import get_ticket, TicketError
            case_id = previous['case_id']
            if get_ticket(conn,case_id)['state'] in ('resolved','closed'):
                raise TicketError('reopen_required','Reopen the existing support ticket before re-investigation.')
    outcome = MultiComponentAgent(conn).run(session_id,complaint=complaint)
    result = outcome.result

    def store(c, case_id=None, diagnosis_id=None):
        result['case_id'] = case_id
        c.execute('INSERT INTO communication_diagnoses(session_id,result_json,case_id) VALUES (?,?,?)',
                  (session_id, json.dumps(result, sort_keys=True), case_id))

    if result['classification'] == 'normal' and complaint is None and case_id is None:
        try:
            conn.execute('BEGIN IMMEDIATE')
            store(conn)
            conn.commit()
        except Exception:
            conn.rollback()
            raise
    else:
        # A callback participates in the existing case transaction: both the
        # monitoring result and feedback-compatible case commit together.
        diagnose_and_persist(conn, outcome.agent_run.state.complaint,case_id=case_id, agent_run=outcome.agent_run, after_persist=store)
    return result
