"""Reviewer feedback: resolution, learning apply (incl. tool priors) and revert."""
import pytest

from app.services import feedback as fb
from app.services.diagnosis import diagnose_and_persist
from app.services.intake import build_complaint
from tests.conftest import template_of


def _persist_case(conn, ds, template):
    item = next(i for i in ds.complaints() if template_of(i, ds) == template)
    out = diagnose_and_persist(conn, build_complaint(dict(item["payload"])))
    return out["case_id"], item["ground_truth"]


def test_apply_learning_inserts_priors_and_logs_changes(conn, dataset):
    """Regression: applying learning crashed with 'Incorrect number of bindings'
    when a tool prior was inserted for the first time."""
    case_id, truth = _persist_case(conn, dataset, "T11")
    r = fb.create_resolution(conn, case_id, {
        "reviewer_id": "rev-test", "verified_root_cause": truth,
        "corrective_action": "verified"})
    out = fb.apply_verified_outcome(conn, r["resolution_id"])
    assert out["applied"] and out["changes"]
    assert conn.execute("SELECT COUNT(*) c FROM tool_priors").fetchone()["c"] > 0
    assert conn.execute("SELECT COUNT(*) c FROM knowledge_changes").fetchone()["c"] > 0
    # idempotent
    again = fb.apply_verified_outcome(conn, r["resolution_id"])
    assert again["already_applied"] and not again["applied"]


def test_revert_restores_previous_prior(conn, dataset):
    import json
    case_id, truth = _persist_case(conn, dataset, "T11")
    r = fb.create_resolution(conn, case_id, {
        "reviewer_id": "rev-test", "verified_root_cause": truth,
        "corrective_action": "verified"})
    fb.apply_verified_outcome(conn, r["resolution_id"])
    ch = next(c for c in fb.list_changes(conn) if c["change_type"] == "prior_update")
    old = json.loads(ch["old_value_json"])["usefulness_score"]
    new = json.loads(ch["new_value_json"])["usefulness_score"]
    assert old != new
    fb.revert_change(conn, ch["change_id"])
    now = conn.execute("SELECT usefulness_score s FROM tool_priors WHERE tool_name=? "
                       "AND category=?", (ch["tool_name"], ch["category"])).fetchone()
    if json.loads(ch['old_value_json']).get('existed', True):
        assert now['s'] == pytest.approx(old)
    else:
        assert now is None
    with pytest.raises(fb.FeedbackError):          # cannot revert twice
        fb.revert_change(conn, ch["change_id"])


def test_unauthorised_reviewer_rejected(conn, dataset):
    case_id, truth = _persist_case(conn, dataset, "T01")
    with pytest.raises(fb.FeedbackError):
        fb.create_resolution(conn, case_id, {
            "reviewer_id": "nobody", "verified_root_cause": truth,
            "corrective_action": "x"})
