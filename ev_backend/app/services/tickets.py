"""Support workflow on existing case IDs; all assignments are local and audited."""
import json
import uuid
from pathlib import Path

from app.core.transactions import atomic

POLICY_FILE = Path(__file__).resolve().parents[1] / 'config' / 'support_policy.json'
STATES = ('new', 'investigating', 'awaiting_evidence', 'assigned', 'escalated', 'resolved', 'closed')
TRANSITIONS = {
    'new': {'investigating','awaiting_evidence','assigned','escalated'},
    'investigating': {'awaiting_evidence','assigned','escalated','resolved'},
    'awaiting_evidence': {'investigating','assigned','escalated','resolved'},
    'assigned': {'investigating','awaiting_evidence','escalated','resolved'},
    'escalated': {'investigating','awaiting_evidence','assigned','resolved'},
    'resolved': {'closed','investigating'}, 'closed': {'investigating'},
}


class TicketError(ValueError):
    def __init__(self, code, message, status=409):
        super().__init__(message)
        self.code, self.status = code, status


def policy():
    return json.loads(POLICY_FILE.read_text(encoding='utf-8'))


@atomic
def open_ticket(conn,complaint,*,case_id=None):
    case_id=case_id or 'C-'+uuid.uuid4().hex[:16].upper()
    conn.execute("INSERT INTO cases(case_id,app_id,complaint_text_redacted,complaint_ts,reported_error,reported_payment_status,reported_session_ref,reported_station_id,user_ref,data_origin,status) VALUES (?,?,?,?,?,?,?,?,?,?,'open')",
        (case_id,complaint.app_id,complaint.text_redacted,complaint.complaint_ts,complaint.reported_error,
         complaint.reported_payment_status,complaint.session_ref,complaint.station_id,complaint.user_ref,complaint.data_origin))
    decision=decide({'classification':'inconclusive','unresolved_questions':['Investigate available component logs.']},(),complaint.text_redacted)
    state='escalated' if decision['requires_escalation'] else 'new'
    conn.execute("UPDATE support_tickets SET state=?,priority=?,decision_json=?,version=version+1 WHERE case_id=?",(state,decision['priority'],json.dumps(decision),case_id))
    audit(conn,case_id,'intake_triage','system','Complaint retained before investigation; precautionary priority does not assert a cause.',{'state':'new'},decision|{'state':state})
    return case_id


@atomic
def investigation_failed(conn,case_id):
    before=get_ticket(conn,case_id)
    decision=before['decision'] | {'investigation_status':'failed','investigation_notice':'Investigation failed. Any saved diagnosis predates this attempt; obtain evidence or retry.'}
    state = 'escalated' if before['state'] == 'escalated' or before['priority'] in ('P0','P1') else 'awaiting_evidence'
    conn.execute("UPDATE support_tickets SET state=?,decision_json=?,version=version+1,updated_at=strftime('%Y-%m-%dT%H:%M:%fZ','now') WHERE case_id=?",(state,json.dumps(decision),case_id))
    audit(conn,case_id,'investigation_failed','system','Investigation did not complete; complaint retained for human review.',before,{'state':state})


def decide(diagnosis, events=(), complaint='', config=None):
    """Pure policy over diagnostic observations, not labels or simulator config."""
    cfg = config or policy()
    root, category = diagnosis.get('root_cause'), diagnosis.get('category')
    component = diagnosis.get('component_type')
    certain = diagnosis.get('classification') in ('probable','confirmed','normal')
    evidence = diagnosis.get('evidence', [])
    # A claimed cause is not evidence. For correlated sessions, every cited event
    # must actually exist in this session, and the citation must support the
    # asserted mechanism. Historical legacy checks use their source references.
    known_events = {e['event_id']: e for e in events}
    support_items = [e for e in evidence if e.get('root_cause', root) == root
                     and e.get('component_type', component) == component]
    if known_events:
        supported = certain and any(
            e.get('event_ids') and all(event_id in known_events for event_id in e['event_ids'])
            for e in support_items)
        if root == 'none':
            # Absence of a detected error alone cannot prove normal completion.
            completed = any(e['event_type'] == 'session.state_changed' and
                            e['payload'].get('to') == 'completed' for e in events)
            paid = any(e['event_type'] == 'payment.result' and
                       e['status'] == 'captured' for e in events)
            supported = supported and completed and paid
    else:
        # Legacy evidence is only trusted after refresh() resolves its source
        # reference against the actual case-linked database record.
        supported = certain and root != 'none' and any(e.get('validated_ref')
            and e.get('kind') == 'matching' and e.get('supports_category') == category
            for e in support_items)
    if not supported:
        category, component = None, None
    team = cfg['component_teams'].get(component, cfg['category_teams'].get(category, 'triage')) if supported else 'triage'
    affected = sorted({e['component_type'] for e in events if e['severity'] in ('warning','error','critical')})
    supporting = sorted({cfg['component_teams'][c] for c in affected if c in cfg['component_teams']} - {team})
    reasons = ['Unique supported owner: ' + team if team != 'triage' else 'Evidence does not establish a unique specialist owner; human triage required.']
    priority = 'P3' if root == 'none' and supported else 'P2'
    safety = [e for e in events if e['event_type'] in ('bms.fault','connector.fault') or e['severity'] == 'critical']
    urgent_report = any(term in complaint.lower() for term in cfg['urgent_report_terms'])
    if urgent_report:
        priority = 'P0'
        reasons.append('Customer reports a potential immediate safety hazard; urgent human triage is precautionary, not a verified cause.')
    elif safety:
        priority = 'P1'
        reasons.append('Observed safety fault requires prompt triage even if root attribution remains inconclusive.')
    elif any(e['event_type'] == 'payment.result' and e['payload'].get('amount', 0) >= cfg['large_financial_amount'] and e['status'] != 'captured' for e in events):
        priority = 'P1'
        reasons.append('Potential financial impact exceeds configured local threshold.')
    elif any(e['event_type'] == 'session.state_changed' and e['payload'].get('from') == 'charging'
             and e['payload'].get('to') in ('stopped','failed') for e in events):
        priority = 'P1'
        reasons.append('Charging was interrupted after energy delivery began.')
    else:
        reasons.append('Completed without established fault.' if priority == 'P3' else 'Charging/customer impact requires standard investigation; insufficient evidence is not treated as low impact.')
    escalation = priority in ('P0','P1')
    if urgent_report:
        if team != 'triage':
            supporting = sorted(set(supporting + [team]))
        team = 'triage'
        reasons.append('Immediate safety reports are owned by triage pending human confirmation.')
    cited_ids = {i for item in support_items for i in item.get('event_ids', [])}
    cited_ids &= known_events.keys()
    contradictory = [item['description'] for item in evidence if item.get('kind') == 'conflicting']
    return {'policy_version':cfg['version'], 'classification': 'inconclusive' if urgent_report else category or ('no_fault_established' if root == 'none' and supported else 'inconclusive'),
            'diagnostic_classification':diagnosis.get('classification','inconclusive'), 'originating_component':component,
            'affected_components':affected, 'assigned_team':team,'supporting_teams':supporting,'priority':priority,
            'requires_escalation':escalation,'requires_human_review':team == 'triage' or escalation,
            'reasons':reasons, 'missing_evidence':diagnosis.get('unresolved_questions', []),
            'contradictory_evidence':contradictory,
            'downstream_symptoms':sorted({e['event_type'] for e in events
                if e['severity'] in ('warning','error','critical') and e['component_type'] != component}),
            'evidence':[{'event_id':e['event_id'],'timestamp':e['timestamp'],'component_type':e['component_type']}
                        for e in events if e['event_id'] in cited_ids],
            'delivery_scope':'Local internal assignment only; no external message or ticket was sent.'}



def _validate_legacy_sources(conn, run, evidence, category):
    """Resolve positive older-agent evidence to real, case-scoped source rows.

    Older tools cite a row ID or sometimes a session ID instead of a structured
    communication event. Only linked rows can justify specialist ownership.
    This adapter does not consult synthetic ground-truth or scenario labels.
    """
    session = run.state.matched_session or {}
    sid = session.get('session_id') or run.state.complaint.session_ref
    charger = session.get('charger_id') or run.state.complaint.station_id
    found = []
    for item in evidence:
        if item.get('kind') != 'matching' or item.get('supports_category') != category:
            continue
        table, ref = item.get('source_table'), item.get('source_ref')
        if not ref or table not in ('session_events','charging_sessions','payment_records','charger_status_log'):
            continue
        ref = str(ref)
        row = None
        if table == 'charging_sessions':
            if sid and sid == ref:
                row = conn.execute('SELECT session_id AS id, COALESCE(end_ts,start_ts) AS ts FROM charging_sessions WHERE session_id=?', (sid,)).fetchone()
        elif table == 'session_events' and sid:
            if ref.isdecimal():
                row = conn.execute('SELECT event_id AS id,event_ts AS ts FROM session_events WHERE event_id=? AND session_id=?',(int(ref),sid)).fetchone()
            elif ref == sid or (charger and ref == charger):
                row = conn.execute('SELECT event_id AS id,event_ts AS ts FROM session_events WHERE session_id=? ORDER BY event_ts LIMIT 1',(sid,)).fetchone()
        elif table == 'payment_records' and sid and ref.isdecimal():
            row = conn.execute('SELECT payment_id AS id,ts FROM payment_records WHERE payment_id=? AND session_id=?',(int(ref),sid)).fetchone()
        elif table == 'charger_status_log' and ref.isdecimal() and charger:
            row = conn.execute('SELECT id,ts FROM charger_status_log WHERE id=? AND (charger_id=? OR station_id=?)',(int(ref),charger,charger)).fetchone()
        if row:
            item['validated_ref'] = True
            found.append({'event_id':f'{table}:{row["id"]}','timestamp':row['ts'],
                          'component_type':'payment' if table=='payment_records' else 'charger',
                          'source_table':table})
    return list({e['event_id']:e for e in found}.values())


def get_ticket(conn, case_id):
    row = conn.execute('SELECT * FROM support_tickets WHERE case_id=?', (case_id,)).fetchone()
    if row is None:
        raise TicketError('ticket_not_found','Support ticket not found.',404)
    data = dict(row)
    data['ticket_id'] = data['case_id']
    data['supporting_teams'] = json.loads(data.pop('supporting_teams_json'))
    data['decision'] = json.loads(data.pop('decision_json'))
    data['history'] = [{**dict(r), 'before':json.loads(r['before_json']), 'after':json.loads(r['after_json'])}
                       for r in conn.execute('SELECT * FROM ticket_history WHERE case_id=? ORDER BY id', (case_id,))]
    return data


def audit(conn, case_id, action, actor, reason, before, after):
    before = {k:v for k,v in before.items() if k!='history'}
    after = {k:v for k,v in after.items() if k!='history'}
    conn.execute('INSERT INTO ticket_history(case_id,action,actor,reason,before_json,after_json) VALUES (?,?,?,?,?,?)',
                 (case_id,action,actor,reason,json.dumps(before),json.dumps(after)))


def refresh(conn, case_id, run):
    current = get_ticket(conn,case_id)
    row = conn.execute('SELECT result_json,session_id FROM communication_diagnoses WHERE case_id=? ORDER BY id DESC LIMIT 1',(case_id,)).fetchone()
    events = []
    if row:
        from app.communication.storage import event_rows
        events = event_rows(conn,row['session_id'])
        result = json.loads(row['result_json'])
    else:
        d = run.diagnosis
        result = {'category':d.primary_category,'classification':d.classification,'evidence':[e.to_dict() for e in run.state.evidence],
                  'unresolved_questions':d.unresolved_questions}
        legacy_citations = _validate_legacy_sources(conn,run,result['evidence'],d.primary_category)
    decision = decide(result,events,run.state.complaint.text_redacted)
    if not row:
        decision['evidence'] = legacy_citations
    decision['investigation_status']='completed'
    latest_diagnosis=conn.execute('SELECT id,version FROM diagnoses WHERE case_id=? ORDER BY version DESC,id DESC LIMIT 1',(case_id,)).fetchone()
    decision['diagnosis_id'],decision['diagnosis_version']=latest_diagnosis['id'],latest_diagnosis['version']
    # Preserve explicit human lifecycle/ownership decisions when re-investigating.
    if current['manual_assignment']:
        decision['assigned_team'],decision['supporting_teams'] = current['assigned_team'],current['supporting_teams']
    if current['manual_priority']:
        decision['priority'] = current['priority']
    if current['manual_assignment'] or current['manual_priority']:
        decision['reasons'].append('Applied human ownership/priority override retained; see ticket audit history.')
    decision['requires_escalation'] = decision['priority'] in ('P0','P1')
    state = 'escalated' if decision['requires_escalation'] or current['state'] == 'escalated' else 'investigating' if result.get('root_cause')=='none' else 'awaiting_evidence' if decision['assigned_team']=='triage' else 'assigned'
    if state == 'escalated':
        decision['requires_escalation'] = True
        decision['requires_human_review'] = True
        if current['state'] == 'escalated' and decision['priority'] not in ('P0','P1'):
            decision['reasons'].append('Existing escalation remains open until a human explicitly changes its state.')
    conn.execute("UPDATE support_tickets SET state=?,priority=?,assigned_team=?,supporting_teams_json=?,decision_json=?,version=version+1,updated_at=strftime('%Y-%m-%dT%H:%M:%fZ','now') WHERE case_id=?",
                 (state,decision['priority'],decision['assigned_team'],json.dumps(decision['supporting_teams']),json.dumps(decision),case_id))
    audit(conn,case_id,'investigated','agent','; '.join(decision['reasons']),current,decision | {'state':state})


@atomic
def update(conn,case_id,payload):
    before = get_ticket(conn,case_id)
    if payload['version'] != before['version']:
        raise TicketError('stale_ticket','Ticket changed; reload before applying an override.')
    cfg = policy()
    state = payload.get('state') or before['state']
    if state != before['state'] and state not in TRANSITIONS[before['state']]:
        raise TicketError('invalid_transition',f"Cannot transition {before['state']} to {state}.")
    current_diagnosis = conn.execute('SELECT COALESCE(MAX(version),1) FROM diagnoses WHERE case_id=?',(case_id,)).fetchone()[0]
    if state in ('resolved','closed') and not conn.execute('SELECT 1 FROM resolutions WHERE case_id=? AND diagnosis_version=?',(case_id,current_diagnosis)).fetchone():
        raise TicketError('resolution_required','Record a reviewer-verified resolution for the latest investigation using Verify & learn first.')
    team = payload.get('assigned_team') or before['assigned_team']
    supporting = payload.get('supporting_teams') if payload.get('supporting_teams') is not None else before['supporting_teams']
    if team not in cfg['teams'] or not set(supporting) <= cfg['teams'].keys():
        raise TicketError('invalid_team','Select configured support teams.',422)
    supporting = sorted(set(supporting) - {team})
    if state == 'assigned' and team == 'triage':
        raise TicketError('triage_not_specialist','Use awaiting evidence or escalated for an unlocalized triage ticket.',422)
    priority = payload.get('priority') or before['priority']
    changed_assignment = team != before['assigned_team'] or supporting != before['supporting_teams']
    changed_priority = priority != before['priority']
    changed_state = state != before['state']
    if not (changed_assignment or changed_priority or changed_state):
        raise TicketError('no_ticket_change','Change at least one ticket field before saving.')
    decision = dict(before['decision'])
    decision.update(assigned_team=team, supporting_teams=supporting, priority=priority,
                    requires_escalation=state == 'escalated' or priority in ('P0','P1'),
                    requires_human_review=team == 'triage' or state == 'escalated' or priority in ('P0','P1'))
    if changed_assignment or changed_priority:
        decision['human_override'] = {'actor':payload['actor'],'reason':payload['reason'],
                                      'assignment_changed':changed_assignment,'priority_changed':changed_priority}
        decision['reasons'] = [*before['decision'].get('reasons',[]),
                               'Human decision by ' + payload['actor'] + ': ' + payload['reason']]
    conn.execute("""UPDATE support_tickets SET state=?,assigned_team=?,priority=?,supporting_teams_json=?,
                 decision_json=?,manual_assignment=?,manual_priority=?,version=version+1,
                 updated_at=strftime('%Y-%m-%dT%H:%M:%fZ','now'),
                 resolved_at=CASE WHEN ? IN ('new','investigating','awaiting_evidence','assigned','escalated')
                     THEN NULL ELSE resolved_at END,
                 closed_at=CASE WHEN ?='closed' THEN strftime('%Y-%m-%dT%H:%M:%fZ','now') ELSE NULL END
                 WHERE case_id=?""",
        (state,team,priority,json.dumps(supporting),json.dumps(decision),
         int(before['manual_assignment'] or changed_assignment),
         int(before['manual_priority'] or changed_priority),state,state,case_id))
    if before['state'] in ('resolved','closed') and state == 'investigating':
        # Keep earlier reviewer resolutions in history, while the reopened case
        # is no longer advertised as resolved before its new investigation.
        conn.execute("UPDATE cases SET status='awaiting_review' WHERE case_id=?",(case_id,))
    after = get_ticket(conn,case_id)
    if state == 'escalated' and before['state'] != 'escalated':
        audit(conn,case_id,'escalated',payload['actor'],payload['reason'],
              {'state':before['state'],'assigned_team':before['assigned_team'],'priority':before['priority']},
              {'state':state,'assigned_team':team,'supporting_teams':supporting,'priority':priority,
               'delivery_scope':'Internal ticket escalation only'})
    audit(conn,case_id,'human_override',payload['actor'],payload['reason'],before,
          {k:v for k,v in after.items() if k!='history'})
    return get_ticket(conn,case_id)


def resolved(conn,case_id,reviewer_id,reason,verified_category):
    before = get_ticket(conn,case_id)
    system = before['decision'].get('classification')
    # A correction exists only when the system had asserted a different category;
    # an earlier abstention is not recorded as a wrong prediction.
    correction = system not in (None,'inconclusive','no_fault_established') and system != verified_category
    decision=before['decision'] | {'verified_classification':verified_category,'verified_by':reviewer_id,
                                   'reviewer_correction':correction,'system_classification_before_review':system}
    conn.execute("UPDATE support_tickets SET decision_json=?,state='resolved',resolved_at=strftime('%Y-%m-%dT%H:%M:%fZ','now'),updated_at=strftime('%Y-%m-%dT%H:%M:%fZ','now'),version=version+1 WHERE case_id=?",(json.dumps(decision),case_id))
    audit(conn,case_id,'resolved',reviewer_id,reason,before,{'state':'resolved','verified_classification':verified_category,
          'system_classification_before_review':system,'reviewer_correction':correction})


def summary(conn):
    """Queue overview for staff; counts only, derived from stored ticket state."""
    def grouped(column, where=''):
        return {r[0]:r[1] for r in conn.execute(f'SELECT {column},COUNT(*) FROM support_tickets {where} GROUP BY {column}')}
    open_where = "WHERE state NOT IN ('resolved','closed')"
    total = conn.execute('SELECT COUNT(*) FROM support_tickets').fetchone()[0]
    return {'total':total,'by_state':grouped('state'),
            'open_by_priority':grouped('priority',open_where),'open_by_team':grouped('assigned_team',open_where),
            'open_escalated':conn.execute("SELECT COUNT(*) FROM support_tickets WHERE state='escalated'").fetchone()[0],
            'open_awaiting_evidence':conn.execute("SELECT COUNT(*) FROM support_tickets WHERE state='awaiting_evidence'").fetchone()[0],
            'open_in_triage':conn.execute("SELECT COUNT(*) FROM support_tickets WHERE assigned_team='triage' AND state NOT IN ('resolved','closed')").fetchone()[0],
            'human_overrides':conn.execute("SELECT COUNT(DISTINCT case_id) FROM ticket_history WHERE action='human_override'").fetchone()[0],
            'delivery_scope':'Local internal assignments only; no external message or ticket is sent.'}
