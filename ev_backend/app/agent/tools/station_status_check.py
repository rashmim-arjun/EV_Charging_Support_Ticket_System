"""Compare the most recent source snapshots available at the incident time."""
from app.models import CheckResult, Evidence
from app.agent.tools.scope import near_time, parse_time

TOOL_NAME = 'station_status_check'
RELATED_CATEGORIES = ['charger_availability_mismatch', 'incorrect_or_delayed_station_status']
REQUIRES_SESSION = False
DESCRIPTION = 'Compare incident-time app display and network status snapshots.'


def run(conn, state):
    c, s = state.complaint, state.matched_session or {}
    station = s.get('station_id') or c.station_id
    ts = c.complaint_ts or s.get('start_ts')
    if s.get('charger_id'):
        rows = [dict(r) for r in conn.execute('SELECT * FROM charger_status_log WHERE charger_id=? ORDER BY ts DESC', (s['charger_id'],))]
    elif station:
        rows = [dict(r) for r in conn.execute('SELECT * FROM charger_status_log WHERE station_id=? ORDER BY ts DESC', (station,))]
    else:
        rows = []
    rows = near_time(rows, ts, 'ts', hours=72, future_minutes=0)
    chargers = {r['charger_id'] for r in rows}
    if len(chargers) > 1:
        rows = []  # A station with several chargers needs an exact session/charger reference.
    if not rows:
        return CheckResult(TOOL_NAME, 'no_data', 'No unambiguous incident-time status history.',
            signals=['status_data_unavailable'], evidence_items=[Evidence(kind='missing',
                description='Station/charger identifier and timestamp needed for status comparison.', tool_name=TOOL_NAME)])
    net = next((r for r in rows if r['source'] == 'network'), None)
    app = next((r for r in rows if r['source'] == 'app_display'), None)
    signals, evidence = [], []
    available = {'available', 'free', 'online'}
    unavailable = {'offline', 'fault', 'occupied', 'out_of_order'}
    text = c.text_redacted.lower()
    availability_claim = any(x in text for x in ('availab', 'marked free', 'someone else', 'occupied'))
    status_claim = availability_claim or any(x in text for x in ('status', 'offline', 'online', 'stale'))
    if not status_claim:
        return CheckResult(TOOL_NAME, 'ok', 'No status claim to reconcile for this incident.',
            signals=['status_not_claimed'], evidence_items=[Evidence(kind='neutral',
                description='Status snapshot differences alone do not explain an unspecified charging failure.', tool_name=TOOL_NAME)])

    def add(sig, cat, description, row, weight):
        signals.append(sig)
        evidence.append(Evidence(kind='matching', description=description, source_table='charger_status_log',
            source_ref=str(row['id']), supports_category=cat, weight=weight, tool_name=TOOL_NAME, signal_key=sig))

    # A mismatch and a stale feed are overlapping observations, not independent
    # votes for competing causes. Identify what the customer is investigating.
    if net and app and availability_claim and app['reported_status'].lower() in available and net['reported_status'].lower() in unavailable:
        add('status_log_shows_offline_while_app_showed_available', RELATED_CATEGORIES[0],
            f"App showed {app['reported_status']}; network recorded {net['reported_status']} at {net['ts']}.", net, .8)
    elif net and app:
        if net['reported_status'].lower() != app['reported_status'].lower():
            add('reported_status_differs_from_source', RELATED_CATEGORIES[1], 'App display differs from the network snapshot.', net, .65)
        lag = abs((parse_time(net['ts']) - parse_time(app['ts'])).total_seconds()) / 60
        if lag > 30:
            add('status_update_lag_minutes', RELATED_CATEGORIES[1], f'Status snapshots differ by {lag:.0f} minutes.', app, .6)
        if (parse_time(ts) - parse_time(net['ts'])).total_seconds() > 6 * 3600:
            add('no_status_update_since_ts', RELATED_CATEGORIES[1], 'Latest network update is more than six hours old.', net, .55)
    if not signals:
        signals.append('status_consistent')
        evidence.append(Evidence(kind='neutral', description='No status mismatch in the available incident-time snapshots.',
            source_table='charger_status_log', source_ref=str(rows[0]['id']), tool_name=TOOL_NAME, weight=.2))
    return CheckResult(TOOL_NAME, 'ok', ', '.join(signals), findings={'entries': rows[:10]}, evidence_items=evidence, signals=signals)
