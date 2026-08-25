"""Clone / AST similarity tests — the ordering assertions from spec §8.1 and the
regression cases from §8.4 (boilerplate, self-match, temporal direction).
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from genuine.candidates import candidate_from_path
from genuine.models import DirectionConfidence, FileRecord, RepoAnalysis
from genuine.signals.clone import CandidateRepo, detect_clones
from genuine.signals.similarity import compare_python

from conftest import FIXTURES, read_fixture


# --------------------------------------------------------------------------- #
# §8.1 ordering: original vs renamed-copy vs rewritten                         #
# --------------------------------------------------------------------------- #
def test_logic_similarity_ordering():
    original = read_fixture("original/inventory.py")
    renamed = read_fixture("renamed/inventory_renamed.py")
    rewritten = read_fixture("rewritten/warehouse.py")

    copy_cmp = compare_python(original, renamed)
    rewrite_cmp = compare_python(original, rewritten)
    self_cmp = compare_python(original, original)

    # Identical file: near-perfect on both axes.
    assert self_cmp.logic_similarity > 0.95

    # Renamed copy: high logic similarity (identifiers are normalized away)...
    assert copy_cmp.logic_similarity > 0.60
    # ...and strictly higher than an honest rewrite of the same problem.
    assert copy_cmp.logic_similarity > rewrite_cmp.logic_similarity + 0.15


def test_structural_vs_logic_separation_on_boilerplate():
    """§8.4-2: shared framework skeleton → HIGH structural, LOW logic."""
    app_a = read_fixture("boilerplate/app_a.py")
    app_b = read_fixture("boilerplate/app_b.py")
    cmp = compare_python(app_a, app_b)

    assert cmp.structural_similarity > cmp.logic_similarity
    # Structure is clearly shared...
    assert cmp.structural_similarity > 0.40
    # ...but the logic is not a copy.
    assert cmp.logic_similarity < 0.55


def test_unrelated_files_score_low():
    inventory = read_fixture("original/inventory.py")
    app = read_fixture("boilerplate/app_a.py")
    cmp = compare_python(inventory, app)
    assert cmp.logic_similarity < 0.5


# --------------------------------------------------------------------------- #
# Repo-level detection + guardrails                                            #
# --------------------------------------------------------------------------- #
def _target_from_fixture(dir_rel: str, owner: str, name: str, created_at=None) -> tuple[RepoAnalysis, dict]:
    root = FIXTURES / dir_rel
    texts = {}
    files = []
    for fp in sorted(root.glob("*.py")):
        rel = fp.name
        src = fp.read_text(encoding="utf-8")
        texts[rel] = src
        files.append(
            FileRecord(path=rel, language="python", loc=len(src.splitlines()), significance_rank=1)
        )
    analysis = RepoAnalysis(
        repo_url=str(root),
        owner=owner,
        repo_name=name,
        ingested_at=datetime.now(timezone.utc),
        repo_created_at=created_at,
        files=files,
    )
    return analysis, texts


def test_copied_repo_scores_higher_than_boilerplate_repo():
    target, texts = _target_from_fixture("original", "alice", "inventory")

    copied = CandidateRepo(
        slug="bob/store",
        owner="bob",
        files={"inventory_renamed.py": read_fixture("renamed/inventory_renamed.py")},
        created_at=datetime(2020, 1, 1, tzinfo=timezone.utc),  # predates target (unknown)
    )
    boiler = CandidateRepo(
        slug="carol/webapp",
        owner="carol",
        files={"app_b.py": read_fixture("boilerplate/app_b.py")},
        created_at=datetime(2020, 1, 1, tzinfo=timezone.utc),
    )

    copied_result = detect_clones(target, texts, [copied])
    boiler_result = detect_clones(target, texts, [boiler])
    assert copied_result.score > boiler_result.score
    assert copied_result.score > 0.4


def test_self_match_excluded():
    """§8.4-4: analyzing a repo must never return itself as a clone candidate."""
    target, texts = _target_from_fixture("original", "alice", "inventory")
    # A candidate that IS the same repo/owner.
    self_cand = CandidateRepo(
        slug="alice/inventory", owner="alice", files=dict(texts),
        created_at=datetime(2019, 1, 1, tzinfo=timezone.utc),
    )
    result = detect_clones(target, texts, [self_cand])
    assert "alice/inventory" in result.self_excluded
    assert result.score == 0.0
    assert result.matches == []


def test_same_owner_excluded():
    """Self-match guard also covers other repos from the same owner."""
    target, texts = _target_from_fixture("original", "alice", "inventory")
    sibling = CandidateRepo(
        slug="alice/other-project", owner="alice",
        files={"inventory_renamed.py": read_fixture("renamed/inventory_renamed.py")},
    )
    result = detect_clones(target, texts, [sibling])
    assert "alice/other-project" in result.self_excluded


def test_temporal_direction_downweights_newer_candidate():
    """§8.4-5: a candidate created AFTER the target can't mean 'target copied'."""
    target, texts = _target_from_fixture(
        "original", "alice", "inventory", created_at=datetime(2020, 1, 1, tzinfo=timezone.utc)
    )
    renamed = read_fixture("renamed/inventory_renamed.py")

    older = CandidateRepo(
        slug="bob/older", owner="bob", files={"x.py": renamed},
        created_at=datetime(2019, 1, 1, tzinfo=timezone.utc),  # predates → target likely copied
    )
    newer = CandidateRepo(
        slug="dave/newer", owner="dave", files={"x.py": renamed},
        created_at=datetime(2021, 1, 1, tzinfo=timezone.utc),  # postdates → candidate likely copied
    )

    older_result = detect_clones(target, texts, [older])
    newer_result = detect_clones(target, texts, [newer])

    assert older_result.matches[0].direction_confidence == DirectionConfidence.TARGET_LIKELY_COPIED
    assert newer_result.matches[0].direction_confidence == DirectionConfidence.CANDIDATE_LIKELY_COPIED
    # Same raw similarity, but the newer candidate is heavily down-weighted.
    assert older_result.score > newer_result.score


def test_candidate_from_path_excludes_vendor(tmp_path):
    (tmp_path / "main.py").write_text("print('hi')\n", encoding="utf-8")
    vendored = tmp_path / "node_modules" / "dep"
    vendored.mkdir(parents=True)
    (vendored / "index.js").write_text("module.exports = 1\n", encoding="utf-8")

    cand = candidate_from_path(tmp_path, slug="x/y", owner="x")
    assert "main.py" in cand.files
    assert not any("node_modules" in p for p in cand.files)
