"""Persist raw observations and separate truth annotations; project visible facts for legacy agents."""
import json
from app.core.transactions import atomic


def event_rows(conn, session_id):
    rows = conn.execute('SELECT * FROM communication_events WHERE session_id=? ORDER BY timestamp,sequence', (session_id,)).fetchall()
    return [{**{k: r[k] for k in r.keys() if k != 'payload_json'}, 'payload': json.loads(r['payload_json'])} for r in rows]


def get_session(conn, session_id):
    row = conn.execute('SELECT * FROM communication_sessions WHERE session_id=?', (session_id,)).fetchone()
    if row is None:
        raise LookupError('Charging simulation session does not exist')
    return {**{k: row[k] for k in row.keys() if k != 'components_json'}, 'components': json.loads(row['components_json'])}


def _legacy_session(conn, session):
    """Translate actual visible events into the existing diagnostic tables.

    Never inspect session['truth'], scenario IDs or simulator failure profiles.
    This gives frozen legacy agents a compatible, truthful observation view.
    """
    events, sid = session['events'], session['session_id']
    components = session['components']
    kinds = {e['event_type'] for e in events}
    states = [e for e in events if e['event_type'] == 'session.state_changed']
    meters = [e for e in events if e['event_type'] == 'meter.sample']
    invoices = [e for e in events if e['event_type'] == 'invoice.created']
    payment = next((e for e in reversed(events) if e['event_type'] == 'payment.result'), None)
    energy = meters[-1]['payload']['energy_kwh'] if meters else 0
    status = states[-1]['payload']['to'] if states else 'unknown'
    reason = states[-1]['payload']['reason'] if states else None
    code = 'HW210' if 'connector.fault' in kinds else 'E101' if 'controller.watchdog_timeout' in kinds else None
    user_ref = 'USR-' + sid
    conn.execute('INSERT INTO charging_sessions(session_id,app_id,user_ref,station_id,charger_id,connector_id,start_ts,end_ts,status,energy_kwh,error_code,stop_reason,payment_status,amount,data_origin) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
        (sid, session['app_id'], user_ref, components['charger'], components['charger'], components['connector'],
         session['started_at'], session['ended_at'], status if status != 'stopped' else 'stopped_early', energy,
         code, reason, payment['status'] if payment else 'unknown',
         round(energy * invoices[-1]['payload']['tariff_per_kwh'], 2) if invoices else 0, 'simulated'))
    return user_ref


def _legacy_events(conn, session, user_ref):
    sid, components = session['session_id'], session['components']
    for e in session['events']:
        kind, data = e['event_type'], e['payload']
        event_kind, charger_id = None, components['charger']
        if kind == 'session.state_changed':
            event_kind = {'connected': 'start_request', 'authorized': 'authorize', 'charging': 'started',
                          'completed': 'completed', 'stopped': 'unexpected_end'}.get(data['to'])
        elif kind == 'controller.watchdog_timeout':
            event_kind = 'start_timeout'
        elif kind == 'connector.fault':
            event_kind = 'connector_fault'
        elif kind == 'bms.fault':
            event_kind, charger_id = 'bms_error', 'app:' + session['app_id']
        elif kind == 'transport.dropped' or (kind == 'transport.delivered' and e['status'] == 'delayed'):
            event_kind = 'connection_timeout'
        if event_kind:
            conn.execute("INSERT INTO session_events(session_id,charger_id,event_ts,event_type,detail,data_origin) VALUES (?,?,?,?,?,'simulated')",
                         (sid, charger_id, e['timestamp'], event_kind, json.dumps({'event_id': e['event_id'], 'user_ref': user_ref, **data})))
        if kind in ('charger.status', 'availability.published'):
            conn.execute("INSERT INTO charger_status_log(charger_id,station_id,ts,reported_status,source,data_origin) VALUES (?,?,?,?,?,'simulated')",
                         (components['charger'], components['charger'], e['timestamp'], e['status'], 'network' if kind == 'charger.status' else 'app_display'))
        if kind == 'payment.result':
            conn.execute("INSERT INTO payment_records(session_id,app_id,user_ref,status,amount,ts,reconciliation_status,data_origin) VALUES (?,?,?,?,?,?,?,'simulated')",
                         (sid, session['app_id'], user_ref, e['status'], data['amount'], e['timestamp'], 'settled' if e['status'] == 'captured' else 'disputed'))


@atomic
def persist_dataset(conn, dataset):
    conn.execute('INSERT OR IGNORE INTO communication_runs(run_id,simulator_version,config_json) VALUES (?,?,?)',
                 (dataset['run_id'], dataset['version'], json.dumps(dataset['config'], sort_keys=True)))
    inserted = 0
    for s in dataset['sessions']:
        if conn.execute('SELECT 1 FROM communication_sessions WHERE session_id=?', (s['session_id'],)).fetchone():
            continue
        user_ref = _legacy_session(conn, s)
        conn.execute('INSERT INTO communication_sessions(session_id,run_id,trace_id,app_id,started_at,ended_at,status,components_json) VALUES (?,?,?,?,?,?,?,?)',
                     (s['session_id'], dataset['run_id'], s['trace_id'], s['app_id'], s['started_at'], s['ended_at'], s['status'], json.dumps(s['components'])))
        for e in s['events']:
            columns = [k for k in e if k != 'payload']
            conn.execute(f"INSERT INTO communication_events({','.join(columns)},payload_json) VALUES ({','.join('?' for _ in columns)},?)",
                         [e[k] for k in columns] + [json.dumps(e['payload'], sort_keys=True)])
        truth = s['truth']
        conn.execute('INSERT INTO communication_truth(session_id,template_id,split,annotations_json) VALUES (?,?,?,?)',
                     (s['session_id'], truth['template_id'], truth['split'], json.dumps(truth, sort_keys=True)))
        _legacy_events(conn, s, user_ref)
        inserted += 1
    return {'run_id': dataset['run_id'], 'inserted': inserted, 'total': len(dataset['sessions'])}


def list_sessions(conn, *, run_id=None, page=1, page_size=20):
    where, args = ('WHERE s.run_id=?', [run_id]) if run_id else ('', [])
    total = conn.execute(f'SELECT COUNT(*) FROM communication_sessions s {where}', args).fetchone()[0]
    rows = conn.execute(f'SELECT s.*, (SELECT COUNT(*) FROM communication_events e WHERE e.session_id=s.session_id) AS event_count FROM communication_sessions s {where} ORDER BY s.rowid DESC LIMIT ? OFFSET ?',
                        args + [page_size, (page - 1) * page_size]).fetchall()
    return {'items': [{**{k: r[k] for k in r.keys() if k != 'components_json'}, 'components': json.loads(r['components_json'])} for r in rows],
            'total': total, 'page': page, 'page_size': page_size}
