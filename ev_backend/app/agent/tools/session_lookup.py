"""Resolve an exact session, or compatible identity and incident time; never guess."""
from app.models import CheckResult, Evidence
from app.agent.tools.scope import near_time

TOOL_NAME = "session_lookup"
RELATED_CATEGORIES = ["session_fails_to_start", "session_stops_unexpectedly", "payment_or_billing_failure"]
REQUIRES_SESSION = False
DESCRIPTION = "Locate the exact charging session without guessing among candidates."


def run(conn, state):
    c = state.complaint
    rows = []
    if c.session_ref:
        rows = [dict(r) for r in conn.execute(
            "SELECT * FROM charging_sessions WHERE session_id=? AND app_id=?", (c.session_ref, c.app_id))]
    elif c.user_ref or (c.station_id and c.complaint_ts):
        sql, args = "SELECT * FROM charging_sessions WHERE app_id=?", [c.app_id]
        if c.user_ref:
            sql += " AND user_ref=?"
            args.append(c.user_ref)
        if c.station_id:
            sql += " AND station_id=?"
            args.append(c.station_id)
        rows = [dict(r) for r in conn.execute(sql, args)]
        if c.complaint_ts:
            rows = near_time(rows, c.complaint_ts, "start_ts", hours=24, future_minutes=60)
    if len(rows) == 1:
        s = rows[0]
        state.matched_session = s
        return CheckResult(TOOL_NAME, "ok", f"Matched session {s['session_id']}.",
            findings={"session": s}, signals=["matched_session_found"], evidence_items=[Evidence(
                kind="neutral", description=f"Matched session {s['session_id']} ({s['status']}).",
                source_table="charging_sessions", source_ref=s["session_id"], weight=0.2, tool_name=TOOL_NAME)])
    ambiguous = len(rows) > 1
    return CheckResult(TOOL_NAME, "no_data", "Multiple plausible sessions; exact reference required." if ambiguous else "No matching session found.",
        findings={"candidate_count": len(rows)}, signals=["ambiguous_sessions" if ambiguous else "no_matching_session"],
        evidence_items=[Evidence(kind="missing", description="Exact session reference required." if ambiguous else "No session matches the supplied identifiers and time.",
            source_table="charging_sessions", weight=0.4, tool_name=TOOL_NAME)])
