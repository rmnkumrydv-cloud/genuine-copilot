"""Shared-registry tests (spec §6.4, §8.4-7): near-duplicate detection between
submissions, and the isolation guard that stops a repo matching itself."""

from __future__ import annotations

from datetime import datetime, timezone

from genuine.ingestion.fingerprint import build_minhash, signature
from genuine.models import RepoAnalysis
from genuine.signals.registry import check, register
from genuine.store import init_schema

from conftest import read_fixture


def _analysis(owner, name, text, fp_text=None) -> RepoAnalysis:
    fp = signature(build_minhash([fp_text if fp_text is not None else text]))
    return RepoAnalysis(
        repo_url=f"https://github.com/{owner}/{name}",
        owner=owner,
        repo_name=name,
        ingested_at=datetime.now(timezone.utc),
        fingerprint=fp,
    )


def test_duplicate_submission_detected(tmp_db):
    init_schema(tmp_db)
    original_text = read_fixture("original/inventory.py")

    first = _analysis("alice", "inventory", original_text)
    register(tmp_db, first)

    # Different user submits the identical code.
    resubmit = _analysis("mallory", "copied-inventory", original_text)
    result = check(tmp_db, resubmit)

    assert result.score > 0.9
    assert result.evidence
    assert result.evidence[0].detail["candidate_slug"] == "alice/inventory"


def test_registry_isolation_no_self_match(tmp_db):
    """§8.4-7: re-checking an already-registered repo must not match itself."""
    init_schema(tmp_db)
    a = _analysis("alice", "inventory", read_fixture("original/inventory.py"))
    register(tmp_db, a)
    result = check(tmp_db, a)  # same slug/owner
    assert result.score == 0.0
    assert result.evidence == []


def test_distinct_repos_score_low(tmp_db):
    init_schema(tmp_db)
    register(tmp_db, _analysis("alice", "inventory", read_fixture("original/inventory.py")))
    other = _analysis("bob", "webapp", read_fixture("boilerplate/app_a.py"))
    result = check(tmp_db, other)
    assert result.score < 0.5


def test_register_is_idempotent(tmp_db):
    init_schema(tmp_db)
    a = _analysis("alice", "inventory", read_fixture("original/inventory.py"))
    register(tmp_db, a)
    register(tmp_db, a)  # upsert, not duplicate row
    from genuine.store import connect

    with connect(tmp_db) as conn:
        count = conn.execute("SELECT COUNT(*) c FROM submissions").fetchone()["c"]
    assert count == 1
