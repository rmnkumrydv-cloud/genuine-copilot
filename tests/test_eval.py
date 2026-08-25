"""Evaluation harness + corpus tests (spec §8.3 / §8.4, Gate 7).

Two promises are locked in here:

* the tuning/held-out split is disjoint, non-empty, and category-complete, so
  reported numbers can't leak from the tuning set (§8.4-6); and
* the real deterministic pipeline produces the right verdict on every labeled
  case, including the named regressions (§8.4): a lone genuine commit is never
  flagged (-1), shared boilerplate stays clean (-2), and a copy wearing a
  fake-git-history timeline is still flagged on clone similarity alone (-3).

A single module-scoped ``run_eval("all")`` materializes real git repos and runs
the real pipeline over the whole corpus; the pipeline assertions read off that
one pass. The metric-math tests use hand-built pairs and need no pipeline.
"""

from __future__ import annotations

import json

import pytest

from genuine.cli import main
from genuine.eval import (
    HELDOUT,
    TUNING,
    assert_no_leakage,
    for_split,
    heldout_set,
    reviewer_time_saved,
    run_eval,
    tuning_set,
)
from genuine.eval import dataset as ds
from genuine.eval.metrics import TriageStats, confusion_from, triage_from
from genuine.models import Verdict


@pytest.fixture(scope="module")
def all_outcomes():
    """Run the real pipeline over the entire corpus exactly once."""
    return {o.repo_id: o for o in run_eval("all").outcomes}


# --------------------------------------------------------------------------- #
# Split integrity / leakage guard (§8.4-6)                                    #
# --------------------------------------------------------------------------- #
def test_split_invariant_holds():
    assert_no_leakage()  # raises AssertionError if the invariant is broken


def test_splits_disjoint_and_cover_corpus():
    tuning = {r.repo_id for r in tuning_set()}
    heldout = {r.repo_id for r in heldout_set()}
    assert tuning and heldout
    assert tuning.isdisjoint(heldout)
    assert tuning | heldout == {r.repo_id for r in ds.CORPUS}


def test_both_splits_contain_every_category():
    for split in (TUNING, HELDOUT):
        assert {r.category for r in for_split(split)} == set(ds.CATEGORIES)


def test_run_eval_rejects_unknown_split():
    with pytest.raises(ValueError):
        run_eval("bogus")


# --------------------------------------------------------------------------- #
# Ground-truth verdicts across the whole corpus                               #
# --------------------------------------------------------------------------- #
def test_no_genuine_repo_is_ever_flagged(all_outcomes):
    """The costly error. An original may be clean or insufficient, never flagged."""
    flagged = [o.repo_id for o in all_outcomes.values()
               if o.authentic and o.verdict == Verdict.FLAGGED]
    assert not flagged, f"falsely flagged genuine repos: {flagged}"


def test_every_copy_is_flagged(all_outcomes):
    copies = [o for o in all_outcomes.values() if o.category == ds.COPIED]
    assert copies
    for o in copies:
        assert o.verdict == Verdict.FLAGGED, f"{o.repo_id} not flagged"


def test_faked_timeline_still_flagged_by_clone(all_outcomes):
    """§8.4-3: a fabricated commit history must not launder copied code — the
    flag has to come from clone similarity, so that sub-score stays high."""
    faked = [o for o in all_outcomes.values() if o.category == ds.FAKED]
    assert faked
    for o in faked:
        assert o.verdict == Verdict.FLAGGED, f"{o.repo_id} not flagged"
        assert o.sub_scores["clone_similarity"] >= 0.8


def test_single_genuine_commit_is_insufficient(all_outcomes):
    """§8.4-1: thin history alone is never grounds to flag."""
    assert all_outcomes["orig-thin"].verdict == Verdict.INSUFFICIENT_SIGNAL


def test_shared_boilerplate_stays_clean(all_outcomes):
    """§8.4-2: high structural + low logic similarity is not a clone."""
    for rid in ("orig-boilerplate-a", "orig-boilerplate-b"):
        assert all_outcomes[rid].verdict == Verdict.CLEAN


def test_independent_rewrite_stays_clean(all_outcomes):
    """Same domain as an older repo, rewritten from scratch → low logic sim."""
    assert all_outcomes["orig-rewrite"].verdict == Verdict.CLEAN


def test_whole_corpus_is_classified_correctly(all_outcomes):
    wrong = [o.repo_id for o in all_outcomes.values() if not o.correct]
    assert not wrong, f"misclassified: {wrong}"


# --------------------------------------------------------------------------- #
# Reported metrics come from the held-out split only                          #
# --------------------------------------------------------------------------- #
def test_heldout_has_zero_false_positives(all_outcomes):
    pairs = [(o.authentic, o.verdict) for o in all_outcomes.values() if o.split == HELDOUT]
    m = confusion_from(pairs)
    assert m.total == len(heldout_set())
    assert m.fp == 0
    assert m.false_positive_rate == 0.0


def test_heldout_catches_every_inauthentic_repo(all_outcomes):
    pairs = [(o.authentic, o.verdict) for o in all_outcomes.values() if o.split == HELDOUT]
    t = triage_from(pairs)
    assert t.inauthentic_total > 0
    assert t.detection_rate == 1.0  # flagged OR queued — none slip through as clean


def test_pipeline_is_deterministic(tmp_path):
    """No now()/random on the scoring path: the same case, analyzed twice from
    scratch (fresh db + clone cache), yields an identical verdict and composite.
    Uses a small copied case so the clone-comparison path is exercised too."""
    from genuine.eval.harness import evaluate_repo

    repo = next(r for r in ds.CORPUS if r.repo_id == "copy-csv")

    def once(tag: str):
        base = tmp_path / tag
        (base / "clones").mkdir(parents=True)
        return evaluate_repo(
            repo, work_root=base / "repos",
            db_path=base / "eval.sqlite", cache_root=base / "clones",
        )

    a, b = once("run_a"), once("run_b")
    assert a.verdict == b.verdict == Verdict.FLAGGED
    assert a.composite_score == b.composite_score
    assert a.sub_scores == b.sub_scores


# --------------------------------------------------------------------------- #
# Metric math — hand-built pairs, no pipeline                                 #
# --------------------------------------------------------------------------- #
def test_confusion_matrix_counts_and_rates():
    C, F = Verdict.CLEAN, Verdict.FLAGGED
    pairs = [
        (False, F),  # tp — inauthentic, caught
        (False, F),  # tp
        (True, F),   # fp — genuine, falsely flagged
        (True, C),   # tn
        (False, C),  # fn — inauthentic, missed
    ]
    m = confusion_from(pairs)
    assert (m.tp, m.fp, m.tn, m.fn) == (2, 1, 1, 1)
    assert m.precision == pytest.approx(2 / 3)
    assert m.recall == pytest.approx(2 / 3)
    assert m.false_positive_rate == pytest.approx(1 / 2)


def test_triage_counts_and_detection_rate():
    """review_queue is a 'catch' for detection but not 'auto-resolved'; an
    inauthentic repo landing in insufficient_signal is a genuine miss."""
    pairs = [
        (True, Verdict.CLEAN),                 # auto-resolved, genuine
        (False, Verdict.FLAGGED),              # auto-resolved, caught
        (False, Verdict.NEEDS_HUMAN_REVIEW),   # queued, caught (not auto)
        (False, Verdict.INSUFFICIENT_SIGNAL),  # slipped through
    ]
    t = triage_from(pairs)
    assert (t.total, t.auto_resolved, t.review_queue, t.insufficient) == (4, 2, 1, 1)
    assert t.inauthentic_total == 3
    assert t.inauthentic_caught == 2
    assert t.detection_rate == pytest.approx(2 / 3)


def test_reviewer_time_saved_math():
    t = TriageStats(total=10, auto_resolved=7, review_queue=2, insufficient=1)
    ts = reviewer_time_saved(t, cold_review_min=12.0, glance_min=1.0, assisted_review_min=4.0)
    assert ts["baseline_min"] == pytest.approx(120.0)   # 10 * 12
    assert ts["with_tool_min"] == pytest.approx(16.0)   # (7 + 1) * 1 + 2 * 4
    assert ts["minutes_saved"] == pytest.approx(104.0)
    assert ts["pct_saved"] == pytest.approx(104.0 / 120.0, abs=1e-4)


# --------------------------------------------------------------------------- #
# CLI wiring (Gate 7 deliverable: `genuine eval`)                             #
# --------------------------------------------------------------------------- #
def test_cli_eval_json_and_artifact(tmp_path, capsys):
    """One invocation exercises both output paths: JSON to stdout and the
    Markdown artifact to disk. Uses the cheaper ``tuning`` split — this is a
    wiring smoke test, not the reported number (that comes from heldout)."""
    out = tmp_path / "evaluation.md"
    code = main(["eval", "--split", "tuning", "--json", "--out", str(out)])
    assert code == 0

    payload = json.loads(capsys.readouterr().out)
    assert payload["split"] == "tuning"
    assert payload["confusion"]["false_positive_rate"] == 0.0
    assert payload["triage"]["detection_rate"] == 1.0

    text = out.read_text(encoding="utf-8")
    assert "tuning" in text
    assert "False-positive rate" in text
