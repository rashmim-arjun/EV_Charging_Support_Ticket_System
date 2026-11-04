"""End-to-end API smoke test on a temporary database."""
import pytest

pytest.importorskip("fastapi")
pytest.importorskip("httpx")
from fastapi.testclient import TestClient  # noqa: E402


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("EV_DB_PATH", str(tmp_path / "api.db"))
    from app.main import create_app
    with TestClient(create_app()) as c:
        yield c


def test_complaint_to_diagnosis_to_feedback(client):
    assert client.get("/api/v1/health").json()["db_ok"] is True
    r = client.post("/api/v1/cases", json={
        "app_id": "tata_power_ez_charge",
        "complaint_text": "Money was deducted but the session never started. "
                          "My number is 9812345678."})
    assert r.status_code in (200, 201), r.text
    case = r.json()
    case_id = case["case_summary"]["case_id"]
    assert "9812345678" not in str(case)            # PII redacted
    full = client.get(f"/api/v1/cases/{case_id}").json()
    d = full["diagnosis"]
    assert 0 <= d["evidence_strength"] <= 1
    if d["classification"] in ("inconclusive", "requires_further_investigation"):
        assert d["primary_category"] is None
    trace = client.get(f"/api/v1/cases/{case_id}/trace")
    assert trace.status_code == 200
    res = client.post(f"/api/v1/cases/{case_id}/resolution", json={
        "reviewer_id": "rev-001", "verified_root_cause": "payment_or_billing_failure",
        "corrective_action": "refund"})
    assert res.status_code == 201, res.text
