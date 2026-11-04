"""Incident-scoped evidence lookup. Naive stored timestamps are interpreted as UTC."""
from datetime import datetime, timezone


def parse_time(value):
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt.astimezone(timezone.utc)
    except (ValueError, TypeError):
        return None


def near_time(rows, ts, column, hours=1, future_minutes=60):
    anchor = parse_time(ts)
    if anchor is None:
        return []
    return [r for r in rows if parse_time(r.get(column)) is not None
            and -future_minutes * 60 <= (anchor - parse_time(r[column])).total_seconds() <= hours * 3600]


def scoped_events(conn, state, event_types, app_level=False):
    c, s = state.complaint, state.matched_session or {}
    slots = ",".join("?" for _ in event_types)
    if not app_level and s.get("session_id"):
        return [dict(r) for r in conn.execute(
            f"SELECT * FROM session_events WHERE session_id=? AND event_type IN ({slots}) ORDER BY event_ts",
            (s["session_id"], *event_types))]
    if not app_level or not c.complaint_ts:
        return []
    rows = [dict(r) for r in conn.execute(
        f"SELECT * FROM session_events WHERE charger_id=? AND event_type IN ({slots}) ORDER BY event_ts DESC",
        (f"app:{c.app_id}", *event_types))]
    rows = near_time(rows, c.complaint_ts, "event_ts")
    if c.user_ref:
        rows = [r for r in rows if c.user_ref in (r.get("detail") or "")
                or (r["event_type"] == "app_crash" and "USR-" not in (r.get("detail") or ""))]
    return rows
