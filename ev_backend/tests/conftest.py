"""Shared fixtures: every test gets its own fresh temporary SQLite DB."""
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.data.synthetic_generator import SyntheticDataset, TEMPLATES  # noqa: E402
from app.evaluation.evaluation import _fresh_conn                      # noqa: E402


@pytest.fixture()
def conn(tmp_path):
    c = _fresh_conn(str(tmp_path / "test.db"))
    c.execute("INSERT OR IGNORE INTO reviewers(reviewer_id, name, role, active)"
              " VALUES ('rev-test','Test Reviewer','diagnosis_reviewer',1)")
    c.commit()
    yield c
    c.close()


@pytest.fixture()
def dataset(conn):
    ds = SyntheticDataset(seed=42, n_per_template=2)
    ds.write(conn)
    return ds


def template_of(item, ds):
    idx = int(item["scenario_id"].split("-")[-1])
    return TEMPLATES[(idx - 1) // ds.n_per_template][0]


@pytest.fixture()
def client(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient
    from app.main import create_app
    monkeypatch.setenv('EV_DB_PATH', str(tmp_path / 'api.db'))
    monkeypatch.setenv('EV_REPORT_DIR',str(tmp_path/'reports'))
    with TestClient(create_app()) as client:
        yield client
