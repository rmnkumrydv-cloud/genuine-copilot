"""End-to-end pipeline integration (spec §8.2) + the fabricated-timeline case
(§8.4-3): copied code wrapped in a faked history must still be flagged, driven
by clone similarity."""

from __future__ import annotations

from datetime import datetime, timezone

from genuine.candidates import candidate_from_path
from genuine.models import Verdict
from genuine.pipeline import analyze

from conftest import FIXTURES, read_fixture


def _healthy_commits(files_final: dict, n=6):
    """A handful of commits with irregular times and unique messages."""
    msgs = ["scaffold project", "add core model", "implement add()", "handle edge cases",
            "add docs", "polish", "more tests", "refactor"]
    hours = [0, 20, 51, 77, 130, 190, 240, 300]
    commits = []
    base = datetime(2024, 2, 1, 9, 17, 0, tzinfo=timezone.utc)
    for i in range(n):
        commits.append({"message": msgs[i], "files": files_final, "date":
                        (base.replace(hour=(9 + i) % 24)).strftime("%Y-%m-%d %H:%M:%S +0000")})
    return commits


def test_end_to_end_flagged_on_copied_code(make_git_repo, tmp_db, cache_root):
    """A repo of copied (renamed) code, with an older original as candidate,
    is flagged — driven by clone similarity."""
    renamed = read_fixture("renamed/inventory_renamed.py")
    target = make_git_repo("copied", [
        {"message": "initial commit", "files": {"inventory.py": renamed}, "date": "2024-06-01 10:00:00 +0000"},
        {"message": "tweak", "files": {"inventory.py": renamed + "\n# tweak\n"}, "date": "2024-06-02 14:00:00 +0000"},
        {"message": "more", "files": {"inventory.py": renamed + "\n# more\n"}, "date": "2024-06-05 11:00:00 +0000"},
    ])
    original_candidate = candidate_from_path(
        FIXTURES / "original", slug="alice/inventory", owner="alice",
        created_at=datetime(2020, 1, 1, tzinfo=timezone.utc),  # predates target
    )

    result = analyze(str(target), db_path=tmp_db, cache_root=cache_root,
                     candidates=[original_candidate])

    assert result.score.verdict == Verdict.FLAGGED
    assert result.score.clone_similarity_score > 0.8
    assert any(e.type.value == "clone_match" for e in result.score.evidence)
    assert "FLAGGED" in result.report_text


def test_end_to_end_clean_on_genuine_repo(make_git_repo, tmp_db, cache_root):
    original = read_fixture("original/inventory.py")
    target = make_git_repo("genuine", _healthy_commits({"inventory.py": original}, n=6))

    result = analyze(str(target), db_path=tmp_db, cache_root=cache_root, candidates=[])

    assert result.score.verdict == Verdict.CLEAN
    assert result.score.clone_similarity_score == 0.0


def test_payload_shape(make_git_repo, tmp_db, cache_root):
    repo = make_git_repo("shape", [
        {"message": "init", "files": {"a.py": "def f():\n    return 1\n"}, "date": "2024-01-01 10:00:00 +0000"},
    ])
    payload = analyze(str(repo), db_path=tmp_db, cache_root=cache_root).to_payload()
    for key in ("verdict", "composite_score", "sub_scores", "coverage_ratio",
                "evidence", "report_text", "matcher"):
        assert key in payload
    assert set(payload["sub_scores"]) == {
        "clone_similarity", "readme_consistency", "commit_forensics", "registry_match"
    }


def test_registry_catches_resubmission_across_runs(make_git_repo, tmp_db, cache_root):
    """First submission registers; a different-owner identical repo is caught."""
    code = read_fixture("original/inventory.py")
    first = make_git_repo("first", [
        {"message": "init", "files": {"inventory.py": code}, "date": "2024-01-01 10:00:00 +0000"},
    ])
    analyze(str(first), db_path=tmp_db, cache_root=cache_root)

    # NOTE: local dirs get owner="" so the same-owner guard doesn't suppress this;
    # the fingerprints are identical, so the registry match should fire.
    second = make_git_repo("second", [
        {"message": "init", "files": {"inventory.py": code}, "date": "2024-03-01 10:00:00 +0000"},
    ])
    result = analyze(str(second), db_path=tmp_db, cache_root=cache_root)
    assert result.score.registry_match_score > 0.9
