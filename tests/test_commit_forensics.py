"""Commit-forensics tests, including regression §8.4-1 (single-commit-but-genuine
must never be flagged on commit pattern alone) and §8.4-3 (a fake-git-history
style timeline must be detectable)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from genuine.models import CommitRecord, DiffStats
from genuine.signals.commit_forensics import (
    MIN_RELIABLE_COMMITS,
    analyze_commits,
    confidence,
    fixed_time_of_day,
    interval_regularity,
    message_quality,
)


def _commit(sha, dt, message="implement feature X", email="dev@example.com"):
    return CommitRecord(sha=sha, timestamp=dt, message=message, author_email=email,
                        diff_stats=DiffStats(additions=10, deletions=2, files_changed=1))


def _genuine_history(n=20):
    """Irregular gaps, varied times of day, descriptive unique messages."""
    base = datetime(2023, 3, 1, 9, 13, 7, tzinfo=timezone.utc)
    # pseudo-irregular but deterministic offsets (hours)
    offsets = [0, 5, 27, 31, 50, 78, 96, 100, 140, 168, 175, 200, 233, 251, 300,
               308, 350, 400, 441, 500]
    msgs = [
        "add product dataclass", "wire up inventory add()", "fix off-by-one in remove",
        "handle missing sku gracefully", "add low_stock threshold param",
        "refactor total_worth to sum comprehension", "add unit tests for remove",
        "document Inventory API", "guard against negative quantity",
        "extract Product.total_value", "rename ambiguous var", "add type hints",
        "cache low_stock result", "fix flaky test", "bump coverage to 90pct",
        "add CLI entrypoint", "handle empty inventory", "polish error messages",
        "add integration test", "prepare release",
    ]
    return [
        _commit(f"sha{i}", base + timedelta(hours=offsets[i], minutes=i * 7 % 53), msgs[i])
        for i in range(n)
    ]


def _faked_history(n=30):
    """fake-git-history signature: one commit/day, identical clock time,
    generic duplicated messages (the tool's defaults)."""
    base = datetime(2023, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
    return [_commit(f"sha{i}", base + timedelta(days=i), "update") for i in range(n)]


# --------------------------------------------------------------------------- #
# Regression §8.4-1: thin history can't be flagged on pattern alone            #
# --------------------------------------------------------------------------- #
def test_single_commit_scores_near_zero():
    one = [_commit("a", datetime(2023, 1, 1, 14, 22, 9, tzinfo=timezone.utc), "initial working prototype")]
    result = analyze_commits(one)
    assert result.confidence < 0.2
    assert result.score < 0.15  # confidence damping keeps it far from flagged


def test_confidence_ramps_with_commit_count():
    assert confidence(0) == 0.0
    assert confidence(MIN_RELIABLE_COMMITS) == 1.0
    assert confidence(MIN_RELIABLE_COMMITS // 2) == 0.5
    assert confidence(MIN_RELIABLE_COMMITS * 3) == 1.0  # clamped


def test_few_but_regular_commits_stay_low():
    """3 evenly-spaced commits shouldn't spike — too little to be reliable."""
    base = datetime(2023, 1, 1, 10, 0, 0, tzinfo=timezone.utc)
    commits = [_commit(f"s{i}", base + timedelta(days=i), "update") for i in range(3)]
    result = analyze_commits(commits)
    assert result.score < 0.25


# --------------------------------------------------------------------------- #
# Regression §8.4-3: a faked timeline is detectable                            #
# --------------------------------------------------------------------------- #
def test_faked_history_scores_high():
    result = analyze_commits(_faked_history(30))
    assert result.confidence == 1.0
    assert result.score > 0.6
    assert any(e.detail["component"] == "fixed_time_of_day" for e in result.evidence)


def test_genuine_history_scores_low():
    result = analyze_commits(_genuine_history(20))
    assert result.score < 0.35


def test_genuine_scores_below_faked():
    assert analyze_commits(_genuine_history(20)).score < analyze_commits(_faked_history(30)).score


# --------------------------------------------------------------------------- #
# Component units                                                              #
# --------------------------------------------------------------------------- #
def test_fixed_time_component_detects_identical_clock():
    high = analyze_commits(_faked_history(20))
    assert fixed_time_of_day(_faked_history(20)) > 0.6
    assert high.components["fixed_time_of_day"] > 0.6


def test_message_quality_flags_generic_duplicates():
    base = datetime(2023, 1, 1, 3, 0, 0, tzinfo=timezone.utc)
    commits = [_commit(f"s{i}", base + timedelta(hours=i * 7), "update") for i in range(10)]
    assert message_quality(commits) > 0.6


def test_interval_regularity_zero_for_bursty():
    assert interval_regularity(_genuine_history(20)) < 0.6
