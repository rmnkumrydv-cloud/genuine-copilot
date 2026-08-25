"""Scoring aggregator tests (spec §8.1, Gate 3).

Covers all four verdict branches AND the load-bearing property for the pitch:
changing a weight in rules.yaml changes the verdict with no code change.
"""

from __future__ import annotations

import textwrap

import pytest

from genuine.models import Verdict
from genuine.scoring import Rulebook, aggregate, composite_score, decide_verdict


@pytest.fixture
def rb() -> Rulebook:
    return Rulebook.load()


# --------------------------------------------------------------------------- #
# Four verdict branches                                                        #
# --------------------------------------------------------------------------- #
def test_clean_verdict(rb):
    r = aggregate(clone_similarity=0.05, readme_consistency=0.0, commit_forensics=0.1,
                  registry_match=0.0, coverage_ratio=0.9, commit_count=25, rulebook=rb)
    assert r.verdict == Verdict.CLEAN


def test_flagged_verdict_driven_by_clone(rb):
    """A dominant clone signal flags via the critical-signal override — even
    though the weighted composite stays *below* ``flagged`` (clone's contribution
    is capped at its 0.45 weight). The flag is NOT from crossing the composite
    line; that is the whole point of the override (see rules.yaml critical_signals)."""
    r = aggregate(clone_similarity=0.95, readme_consistency=0.2, commit_forensics=0.1,
                  registry_match=0.3, coverage_ratio=0.9, commit_count=25, rulebook=rb)
    assert r.verdict == Verdict.FLAGGED
    assert r.clone_similarity_score >= rb.critical["clone_similarity"]
    assert r.composite_score < rb.flagged  # flagged by override, not by composite


def test_flagged_verdict_via_composite(rb):
    """The *normal* flag path: several signals moderately high push the weighted
    composite over ``flagged`` with no single signal tripping its critical cutoff."""
    r = aggregate(clone_similarity=0.8, readme_consistency=0.8, commit_forensics=0.8,
                  registry_match=0.8, coverage_ratio=0.9, commit_count=25, rulebook=rb)
    assert r.clone_similarity_score < rb.critical["clone_similarity"]
    assert r.registry_match_score < rb.critical["registry_match"]
    assert r.composite_score >= rb.flagged
    assert r.verdict == Verdict.FLAGGED


def test_needs_human_review_band(rb):
    # Compose sub-scores landing composite in [review_low, flagged).
    r = aggregate(clone_similarity=0.55, readme_consistency=0.5, commit_forensics=0.5,
                  registry_match=0.5, coverage_ratio=0.9, commit_count=25, rulebook=rb)
    assert rb.review_low <= r.composite_score < rb.flagged
    assert r.verdict == Verdict.NEEDS_HUMAN_REVIEW


def test_insufficient_signal_on_thin_coverage(rb):
    r = aggregate(clone_similarity=0.1, readme_consistency=0.0, commit_forensics=0.1,
                  registry_match=0.0, coverage_ratio=0.2, commit_count=25, rulebook=rb)
    assert r.verdict == Verdict.INSUFFICIENT_SIGNAL


def test_insufficient_signal_on_thin_history(rb):
    r = aggregate(clone_similarity=0.1, readme_consistency=0.0, commit_forensics=0.05,
                  registry_match=0.0, coverage_ratio=0.9, commit_count=1, rulebook=rb)
    assert r.verdict == Verdict.INSUFFICIENT_SIGNAL


def test_strong_copy_over_thin_coverage_still_flags(rb):
    """§6.2: thin coverage downgrades to insufficient ONLY if not already flagged.
    A blatant clone with low coverage must still flag."""
    r = aggregate(clone_similarity=0.98, readme_consistency=0.3, commit_forensics=0.2,
                  registry_match=0.5, coverage_ratio=0.1, commit_count=1, rulebook=rb)
    assert r.verdict == Verdict.FLAGGED


# --------------------------------------------------------------------------- #
# Composite math                                                               #
# --------------------------------------------------------------------------- #
def test_composite_is_weighted_sum(rb):
    sub = {"clone_similarity": 1.0, "readme_consistency": 0.0,
           "commit_forensics": 0.0, "registry_match": 0.0}
    # Only clone fires → composite == clone weight (normalized; weights sum to 1).
    assert composite_score(sub, rb) == pytest.approx(rb.weights["clone_similarity"], abs=1e-6)


def test_composite_bounded_0_1(rb):
    allmax = {k: 1.0 for k in rb.weights}
    allzero = {k: 0.0 for k in rb.weights}
    assert composite_score(allmax, rb) == pytest.approx(1.0, abs=1e-6)
    assert composite_score(allzero, rb) == 0.0


# --------------------------------------------------------------------------- #
# The pitch property: weights are DATA, not code (Gate 3)                      #
# --------------------------------------------------------------------------- #
def test_weights_are_data_not_code(tmp_path):
    """Editing rules.yaml alone must change the verdict — no code change."""
    scores = dict(clone_similarity=0.5, readme_consistency=0.0,
                  commit_forensics=0.0, registry_match=0.0,
                  coverage_ratio=0.9, commit_count=25)

    low_yaml = textwrap.dedent("""
        weights: {clone_similarity: 0.45, registry_match: 0.20, readme_consistency: 0.20, commit_forensics: 0.15}
        thresholds: {flagged: 0.65, review_low: 0.45}
        insufficient_signal: {min_commits: 3, min_coverage: 0.35}
    """)
    high_yaml = textwrap.dedent("""
        weights: {clone_similarity: 0.95, registry_match: 0.02, readme_consistency: 0.02, commit_forensics: 0.01}
        thresholds: {flagged: 0.65, review_low: 0.45}
        insufficient_signal: {min_commits: 3, min_coverage: 0.35}
    """)
    low_path = tmp_path / "low.yaml"
    high_path = tmp_path / "high.yaml"
    low_path.write_text(low_yaml)
    high_path.write_text(high_yaml)

    low_rb = Rulebook.load(low_path)
    high_rb = Rulebook.load(high_path)

    # Same inputs, same code — only the YAML differs — different verdict.
    low_verdict = aggregate(**scores, rulebook=low_rb).verdict
    high_verdict = aggregate(**scores, rulebook=high_rb).verdict
    assert low_verdict == Verdict.CLEAN          # 0.5 * 0.45 = 0.225 < review_low
    assert high_verdict == Verdict.NEEDS_HUMAN_REVIEW  # 0.5 * 0.95 = 0.475 in band
    assert low_verdict != high_verdict


def test_aggregate_signature_has_no_ai_opinion_param():
    """Structural neuro-symbolic boundary (§6.8): the aggregator physically
    cannot receive an LLM opinion."""
    import inspect

    params = set(inspect.signature(aggregate).parameters)
    forbidden = {"ai_opinion", "llm_opinion", "llm_summary", "ai_summary"}
    assert not (params & forbidden)
