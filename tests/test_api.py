"""FastAPI endpoint tests (Gate 1/6 surface). Settings are pointed at a temp DB
so tests never touch the real registry."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from conftest import FIXTURES


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("GENUINE_DB_PATH", str(tmp_path / "api.sqlite"))
    monkeypatch.setenv("GENUINE_CLONE_CACHE", str(tmp_path / "clones"))
    from genuine.config import get_settings

    get_settings.cache_clear()
    from genuine.api import app

    yield TestClient(app)
    get_settings.cache_clear()


def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_rules_endpoint_exposes_weights(client):
    r = client.get("/rules")
    assert r.status_code == 200
    body = r.json()
    assert body["weights"]["clone_similarity"] == 0.45
    assert body["thresholds"]["flagged"] == 0.65


def test_analyze_local_dir_and_fetch_job(client):
    r = client.post("/analyze", json={"repo_url": str(FIXTURES / "original")})
    assert r.status_code == 200
    payload = r.json()
    assert "verdict" in payload
    assert "job_id" in payload
    assert set(payload["sub_scores"]) == {
        "clone_similarity", "readme_consistency", "commit_forensics", "registry_match"
    }

    # The fixture dir has no git history -> insufficient_signal, never flagged.
    assert payload["verdict"] == "insufficient_signal"

    job = client.get(f"/jobs/{payload['job_id']}")
    assert job.status_code == 200
    assert job.json()["status"] == "done"


def test_unknown_job_404(client):
    assert client.get("/jobs/does-not-exist").status_code == 404


def test_analyze_bad_url_returns_400(client):
    r = client.post("/analyze", json={"repo_url": "not-a-url-or-path"})
    assert r.status_code == 400
