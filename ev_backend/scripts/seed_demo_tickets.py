"""Add 24 realistic, explicitly simulated tickets and correlated component logs.

Existing tickets are retained. Repeating a seed skips its completed fixtures.
Resolutions are fictional demo reviews; no learning or external action is run.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
import json
import logging
from pathlib import Path
import sqlite3
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.communication.catalog import ROOTS
from app.communication.service import diagnose_session
from app.communication.simulator import generate_dataset
from app.communication.storage import persist_dataset
from app.core import db
from app.data.seed_rules import seed_rules_if_empty
from app.services import feedback, tickets
from app.services.intake import build_complaint

DEFAULT_SEED = 20261105
REVIEWER = 'rev-demo-fixtures'
FIXTURE_VERSION = 'realistic-support-demo-v1'

# Authored customer symptoms and fictional follow-up, never model responses.
# The diagnostic engine independently inspects the generated observations.
PLANS = {
    'charger_controller_timeout': (
        ('assigned', 'resolved'),
        ('The charger accepted my start request but stayed on preparing for several minutes. No energy was delivered, and the display eventually showed a timeout.',
         'I tried starting twice at the same connector. The car was plugged in correctly, but the charging screen kept spinning and the session never began.'),
        'Controller logs were reviewed, the start-command timeout was corrected in the demo, and a follow-up start completed.'),
    'vehicle_bms_fault': (
        ('escalated', 'resolved'),
        ('Charging stopped before my target, and the vehicle showed a battery warning. I left the connector alone and need someone to review the session before I try again.',
         'The car started charging normally but stopped after a few minutes with a vehicle warning. Please check whether the stop came from the vehicle or the station.'),
        'The simulated vehicle specialist reviewed the battery safety-stop events and recorded a fictional inspection outcome.'),
    'authorization_conflict': (
        ('assigned', 'closed'),
        ('The charging screen said I was authorized, but the station would not start. I signed in again and still could not begin the session.',
         'My account appeared ready to charge, but the connector never supplied energy. Please check the account authorization for this visit.'),
        'The demo authorization record was reconciled with the app display, and the fictional customer confirmed the corrected status.'),
    'payment_conflict': (
        ('new', 'resolved'),
        ('Charging finished, but the payment status on the receipt is confusing. The app shows a deduction while another screen says payment failed. Please check the transaction.',
         'I received a charging receipt, but the final payment confirmation does not agree with the amount shown in my session. Please reconcile the records.'),
        'The simulated payment and receipt records were reconciled. No actual refund, bank transaction or customer notification occurred.'),
    'connector_fault': (
        ('escalated', 'closed'),
        ('Charging ended unexpectedly and the connector felt unusually warm. I stopped using this point and need the station team to inspect it before another attempt.',
         'The session stopped well before my target and the charging point showed a connector warning. Please inspect this connector and explain the interruption.'),
        'A fictional technician inspection and connector repair were recorded for the generated fault; a simulated follow-up check passed.'),
    'network_delay': (
        ('assigned', 'investigating'),
        ('The car finished charging, but the session remained pending in the app for several minutes. I need the final receipt and charging status checked.',
         'My charging session ended, but the station and account screens updated at different times. The support team is checking the delayed session messages.'),
        'The demo communication delay was reviewed and the delayed charging-session updates were reconciled.'),
    'network_loss': (
        ('assigned', 'closed'),
        ('I plugged in and selected start, but the station did not respond. The app eventually timed out and the car received no energy. Please check this visit.',
         'The start request failed even though the cable was connected. A second attempt showed the same timeout, so I used another charging point.'),
        'The simulated dropped-message incident was reviewed and a fictional connectivity recovery and follow-up session were recorded.'),
    'network_duplicate': (
        ('resolved', 'assigned'),
        ('After charging finished, the app refreshed the payment confirmation more than once. Please confirm whether these repeated updates represent one transaction.',
         'The charging session completed, but the final confirmation appeared repeatedly. Please check for duplicate messages and confirm the payment record.'),
        'The generated retry/duplicate records were reconciled and the demo reviewer confirmed that only one payment side effect was recorded.'),
    'stale_availability': (
        ('new', 'assigned'),
        ('The map showed an available charging point, but another vehicle was already connected when I arrived. Please check the station status before routing more drivers here.',
         'I drove to a point shown as free, but it was occupied. The app still displayed it as available after I refreshed the screen.'),
        'The simulated availability publication was corrected and its station-status refresh was checked.'),
    'metering_mismatch': (
        ('assigned', 'resolved'),
        ('The energy on my charging receipt is higher than the energy shown by the station at the end of the session. Please compare the meter readings with the invoice.',
         'My final bill does not seem to match the delivered energy in the session history. Please check the charging meter and tariff calculation for this visit.'),
        'The generated meter readings and invoice were reconciled in the demo. No real bill or payment was changed.'),
    'inconclusive': (
        ('awaiting_evidence', 'escalated'),
        ('I could not complete charging and the app did not give me a clear explanation. I have the session reference, but the support team still needs the charger-side logs.',
         'I noticed a burning smell near the charging cable and stopped my attempt. Please arrange an urgent review; I do not know which part caused the problem.'),
        'The fictional review remained inconclusive because the required observations were unavailable.'),
    'none': (
        ('closed', 'resolved'),
        ('My vehicle reached the target charge and I received the receipt. Please confirm that the session energy and payment records agree before closing my enquiry.',
         'Charging completed normally, but I would like the support team to check my receipt and confirm that there are no outstanding session issues.'),
        'The simulated reviewer confirmed matching authorization, delivered energy, completed charging and payment observations. No fault was established.'),
}


def _shift_and_namespace(value, identity, delta):
    if isinstance(value, list):
        return [_shift_and_namespace(item, identity, delta) for item in value]
    if isinstance(value, dict):
        return {key: _shift_and_namespace(item, identity, delta) for key, item in value.items()}
    if isinstance(value, str):
        if len(value) > 10 and value[4:5] == '-' and value[10:11] == 'T':
            try:
                instant = datetime.fromisoformat(value.replace('Z', '+00:00'))
                if instant.tzinfo:
                    return (instant + delta).isoformat()
            except ValueError:
                pass
        return value.replace(identity, 'DEMO-' + identity)
    return value


def _fixtures(seed, now):
    source = generate_dataset({'seed': seed, 'split': 'test', 'per_template': 2})
    grouped = defaultdict(list)
    for session in source['sessions']:
        grouped[session['truth']['expected_label']].append(session)
    first = [('network_loss', 0), ('connector_fault', 0), ('payment_conflict', 0),
             ('inconclusive', 0), ('charger_controller_timeout', 0), ('none', 0)]
    order = first + [(root, variant) for root in PLANS for variant in range(2)
                     if (root, variant) not in first]
    result = []
    for index, (root, variant) in enumerate(order):
        age = timedelta(minutes=15 + index * 45) if index < 6 else timedelta(hours=12 + (index - 6) * 14)
        created = now - age
        incident_end = created - timedelta(minutes=6 + index % 11)
        original = grouped[root][variant]
        delta = incident_end - datetime.fromisoformat(original['ended_at'])
        session = _shift_and_namespace(original, original['session_id'][3:], delta)
        session['app_id'] = 'ev_support'
        result.append({'case_id': f'C-DEMO-{seed}-{index + 1:03d}', 'root': root, 'variant': variant,
                       'session': session, 'created': created,
                       'report_delay': 6 + index % 11,
                       'station': f'STN-DEMO-{index % 6 + 1:03d}', 'stage': PLANS[root][0][variant]})
    source.update(run_id='DEMO-' + source['run_id'], sessions=[item['session'] for item in result])
    source['config'] = {**source['config'], 'fixture': FIXTURE_VERSION}
    return source, result


def _finish_timeline(conn, item):
    """Date only this authored fixture's history, never existing user records."""
    cid, created = item['case_id'], item['created']
    stamp = lambda minutes: (created + timedelta(minutes=minutes)).isoformat()
    resolved = item['stage'] in ('resolved', 'closed')
    closed = item['stage'] == 'closed'
    final_minute = 61 if closed else 46 if resolved else 4
    with conn:
        conn.execute('UPDATE cases SET created_at=? WHERE case_id=?', (stamp(0), cid))
        for table in ('diagnoses', 'case_checks', 'communication_diagnoses'):
            conn.execute(f'UPDATE {table} SET created_at=? WHERE case_id=?', (stamp(2), cid))
        conn.execute('UPDATE resolutions SET resolved_at=? WHERE case_id=?', (stamp(45), cid))
        conn.execute("UPDATE ticket_history SET created_at=CASE WHEN action='resolved' THEN ? "
                     "WHEN action='human_override' THEN ? WHEN action='investigated' THEN ? ELSE ? END WHERE case_id=?",
                     (stamp(45), stamp(60 if closed else 3), stamp(2), stamp(0), cid))
        conn.execute('UPDATE support_tickets SET updated_at=?,resolved_at=?,closed_at=? WHERE case_id=?',
                     (stamp(final_minute), stamp(45) if resolved else None, stamp(60) if closed else None, cid))
        tickets.audit(conn, cid, 'demo_seeded', 'simulation-fixture',
                      'Authored simulated support example. Reviews and repairs are fictional; no real external action occurred.',
                      {}, {'fixture': FIXTURE_VERSION, 'seeded_state': item['stage']})
        conn.execute("UPDATE ticket_history SET created_at=? WHERE case_id=? AND action='demo_seeded'", (stamp(final_minute), cid))


def seed_demo_tickets(conn, seed=DEFAULT_SEED, now=None):
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        raise ValueError('The fixture clock must include a timezone.')
    dataset, fixtures = _fixtures(seed, now.astimezone(timezone.utc))
    pending = []
    for item in fixtures:
        cid = item['case_id']
        existing = conn.execute('SELECT data_origin,reported_session_ref FROM cases WHERE case_id=?', (cid,)).fetchone()
        if existing and (existing['data_origin'] != 'simulated' or existing['reported_session_ref'] != item['session']['session_id']):
            raise ValueError('Demo ID conflicts with an existing record: ' + cid)
        if not conn.execute("SELECT 1 FROM ticket_history WHERE case_id=? AND action='demo_seeded'", (cid,)).fetchone():
            pending.append(item)
    if not pending:
        return {'added': 0, 'skipped': len(fixtures), 'tickets': []}

    db.sync_config_tables(conn)
    seed_rules_if_empty(conn)
    conn.execute("INSERT OR IGNORE INTO reviewers(reviewer_id,name,role,active) VALUES (?,?,'demo_reviewer',0)",
                 (REVIEWER, 'Simulated demo reviewer (fictional outcomes)'))
    reviewer = conn.execute('SELECT role FROM reviewers WHERE reviewer_id=?', (REVIEWER,)).fetchone()
    if reviewer['role'] != 'demo_reviewer':
        raise ValueError('The demo reviewer ID is already used by another reviewer.')
    conn.execute('UPDATE reviewers SET active=1 WHERE reviewer_id=?', (REVIEWER,))
    conn.commit()
    saved = []
    try:
        persist_dataset(conn, {**dataset, 'sessions': [item['session'] for item in pending]})
        for item in pending:
            session, cid, root = item['session'], item['case_id'], item['root']
            # Give the generated point a human-readable synthetic station ID.
            conn.execute('UPDATE charging_sessions SET station_id=? WHERE session_id=?', (item['station'], session['session_id']))
            conn.execute('UPDATE charger_status_log SET station_id=? WHERE charger_id=?', (item['station'], session['components']['charger']))
            conn.commit()
            stored = conn.execute('SELECT ended_at FROM communication_sessions WHERE session_id=?', (session['session_id'],)).fetchone()
            # On recovery, retain the already-persisted observation clock.
            item['created'] = datetime.fromisoformat(stored['ended_at']) + timedelta(minutes=item['report_delay'])
            complaint = build_complaint({'app_id': 'ev_support', 'complaint_text': PLANS[root][1][item['variant']],
                'session_ref': session['session_id'], 'station_id': item['station'],
                'complaint_ts': stored['ended_at'], 'data_origin': 'simulated'})
            if not conn.execute('SELECT 1 FROM cases WHERE case_id=?', (cid,)).fetchone():
                tickets.open_ticket(conn, complaint, case_id=cid)
            if item['stage'] != 'new' and not conn.execute('SELECT 1 FROM diagnoses WHERE case_id=?', (cid,)).fetchone():
                diagnose_session(conn, session['session_id'], complaint=complaint, case_id=cid)
            if item['stage'] in ('resolved', 'closed'):
                if not conn.execute('SELECT 1 FROM resolutions WHERE case_id=?', (cid,)).fetchone():
                    feedback.create_resolution(conn, cid, {'reviewer_id': REVIEWER,
                        'verified_root_cause': ROOTS[root][0] or 'no_fault_established',
                        'corrective_action': '[SIMULATED OUTCOME] ' + PLANS[root][2],
                        'resolution_notes': 'Fictional review of generated observations for a dashboard example. No human repair, payment or customer notification took place.'})
            current = tickets.get_ticket(conn, cid)
            # The fictional operator treats the reported burning smell as an
            # urgent precaution, without pretending the missing logs prove it.
            urgent = root == 'inconclusive' and item['stage'] == 'escalated'
            if current['state'] != item['stage'] or urgent and current['priority'] != 'P0':
                tickets.update(conn, cid, {'version': current['version'], 'state': item['stage'],
                    'actor': 'demo-operator', **({'priority': 'P0'} if urgent else {}),
                    'reason': 'Simulated operator requests immediate precautionary review of a reported burning smell; cause remains unverified.' if urgent else 'Simulated support-queue lifecycle example; no real operational action.'})
            _finish_timeline(conn, item)
            saved.append({'ticket_id': cid, 'session_id': session['session_id'], 'state': item['stage'],
                          'priority': tickets.get_ticket(conn, cid)['priority'], 'data_origin': 'simulated'})
    finally:
        conn.execute('UPDATE reviewers SET active=0 WHERE reviewer_id=?', (REVIEWER,))
        conn.commit()
    return {'added': len(saved), 'skipped': len(fixtures) - len(pending),
            'states': dict(Counter(item['state'] for item in saved)), 'tickets': saved}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--db', help='Defaults to EV_DB_PATH or the application database')
    parser.add_argument('--seed', type=int, default=DEFAULT_SEED)
    args = parser.parse_args()
    logging.getLogger('app').setLevel(logging.WARNING)
    path = args.db or db.get_db_path()
    conn = db.connect(path)
    try:
        if Path(path).exists() and conn.execute("SELECT 1 FROM sqlite_master WHERE name='cases'").fetchone():
            backup = Path(path).with_name(Path(path).name + datetime.now().strftime('.backup-demo-%Y%m%d-%H%M%S-%f'))
            target = sqlite3.connect(str(backup))
            try:
                conn.backup(target)
            finally:
                target.close()
            print('Backup:', backup, flush=True)
        db.init_db(conn)
        result = seed_demo_tickets(conn, args.seed)
        result['database'] = str(Path(path).resolve())
        result['total_cases'] = conn.execute('SELECT COUNT(*) FROM cases').fetchone()[0]
        result['integrity'] = conn.execute('PRAGMA integrity_check').fetchone()[0]
        result['foreign_key_violations'] = len(conn.execute('PRAGMA foreign_key_check').fetchall())
        print(json.dumps(result, indent=2))
    finally:
        conn.close()


if __name__ == '__main__':
    main()
