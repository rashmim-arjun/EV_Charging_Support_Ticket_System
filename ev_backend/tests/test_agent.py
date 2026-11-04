"""Core agent behaviour: conflicts, abstention, tool crashes, duplicate guard."""
from app.agent.agent import DiagnosticAgent
from app.agent.tools import payment_check
from app.models import CaseState, Complaint
from app.services.intake import build_complaint
from tests.conftest import template_of

ABSTAIN = ("inconclusive", "requires_further_investigation")


def _run_all(conn, ds):
    for item in ds.complaints():
        yield item, DiagnosticAgent(conn).run(build_complaint(dict(item["payload"])))


def test_planted_conflict_is_recorded_and_never_confirmed(conn, dataset):
    seen = 0
    for item, run in _run_all(conn, dataset):
        if template_of(item, dataset) != "T18":
            continue
        seen += 1
        conflicts = [e for e in run.state.evidence if e.kind == "conflicting"]
        assert conflicts, "planted claim-vs-record conflict must create conflicting evidence"
        assert run.diagnosis.classification != "confirmed"
        assert any("Conflicting evidence" in q for q in run.diagnosis.unresolved_questions)
    assert seen == 2


def test_abstention_asserts_no_root_cause(conn, dataset):
    for _item, run in _run_all(conn, dataset):
        d = run.diagnosis
        if d.classification in ABSTAIN:
            assert d.primary_category is None
            assert d.supporting_evidence_ids == []
        else:
            assert d.primary_category is not None


def test_confirmed_requires_no_conflicts_and_multiple_tools(conn, dataset):
    for _item, run in _run_all(conn, dataset):
        if run.diagnosis.classification == "confirmed":
            assert not [e for e in run.state.evidence if e.kind == "conflicting"]
            tools = {e.tool_name for e in run.state.evidence
                     if e.kind == "matching"
                     and e.supports_category == run.diagnosis.primary_category}
            assert len(tools) >= 2


def test_no_tool_is_run_twice_and_steps_bounded(conn, dataset):
    for _item, run in _run_all(conn, dataset):
        names = [s.tool_name for s in run.trace]
        assert len(names) == len(set(names))
        assert len(run.trace) <= 8


def test_confidence_is_bounded(conn, dataset):
    for _item, run in _run_all(conn, dataset):
        assert 0.0 <= run.diagnosis.evidence_strength <= 1.0


def test_payment_check_does_not_crash_on_deduction_claim(conn):
    """Regression: payment_check used to raise AttributeError for any complaint
    that mentioned a deduction and always returned status='error'."""
    c = Complaint(app_id="tata_power_ez_charge",
                  text_redacted="Money was deducted but charging never started",
                  reported_payment_status="deducted", user_ref="nobody")
    state = CaseState(complaint=c, applicable_categories=["payment_or_billing_failure"])
    res = payment_check.run(conn, state)
    assert res.status != "error", res.summary
    assert "complaint_deducted_no_payment_record" in res.signals


def test_double_charge_is_detected(conn, dataset):
    hits = 0
    for item, run in _run_all(conn, dataset):
        if template_of(item, dataset) == "T06":
            signals = {s for st in run.trace for s in st.result["signals"]}
            hits += "double_charge_same_session" in signals
    assert hits == 2


def test_session_independent_tools_run_without_session(conn):
    """A complaint with no matching session must still run session-independent tools."""
    c = build_complaint({"app_id": "chargezone",
                         "complaint_text": "App keeps crashing and freezing, technical error."})
    run = DiagnosticAgent(conn).run(c)
    assert "app_error_check" in [s.tool_name for s in run.trace]
