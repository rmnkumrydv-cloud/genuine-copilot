"""Commit forensics — deterministic history-authenticity signal (spec §6.3).

Produces a **suspicion** score in ``[0, 1]`` (higher = history looks fabricated)
from a handful of cheap, auditable tells that generators like ``fake-git-history``
and ``Commitose`` leave behind:

* **fixed time-of-day** — the tools stamp every commit at the same clock time
  (often 00:00:00); real work is spread across the day.
* **interval regularity** — evenly spaced commits (one-a-day painting a
  contribution graph) vs. the bursty, irregular cadence of real work.
* **message quality** — generic/duplicated messages, or GitHub's
  "Add files via upload" drag-and-drop default.
* **timestamp collisions** — many commits sharing an exact instant (bulk write).

Two guardrails make this safe (spec §8.4 case 1 — "single-commit-but-genuine
must never be flagged on commit pattern alone"):

1. The whole score is multiplied by a **confidence** factor that ramps from 0
   up to ``MIN_RELIABLE_COMMITS``. Too few commits → statistically meaningless →
   near-zero score.
2. Merge commits are excluded from message analysis so a healthy merge-heavy
   history isn't punished.
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass, field

from ..models import CommitRecord, EvidenceItem, EvidenceType, SubScore

MIN_RELIABLE_COMMITS = 10  # confidence hits 1.0 here; ramps linearly below

# Component weights (sum to 1.0 → raw suspicion stays in [0, 1]).
_W_FIXED_TIME = 0.30
_W_REGULARITY = 0.30
_W_MESSAGE = 0.25
_W_COLLISION = 0.15

# Natural clustering we tolerate before calling it suspicious.
_TIME_BASELINE = 0.25
_COLLISION_BASELINE = 0.10

_GENERIC_MESSAGES = frozenset(
    {
        "update",
        "updates",
        "updated",
        "commit",
        "commits",
        "changes",
        "change",
        "changed",
        "fix",
        "fixes",
        "fixed",
        "wip",
        "stuff",
        "edit",
        "edits",
        "misc",
        ".",
        "..",
        "...",
        "minor",
        "temp",
        "tmp",
        "asdf",
        "test",
        "testing",
        "initial commit",
        "first commit",
        "add files via upload",  # GitHub web drag-and-drop default
    }
)


def _clamp(x: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, x))


def _rescale(value: float, baseline: float) -> float:
    """Map a fraction to [0, 1], treating everything <= baseline as 0."""
    if value <= baseline:
        return 0.0
    return _clamp((value - baseline) / (1.0 - baseline))


# --------------------------------------------------------------------------- #
# Individual, independently-testable components                               #
# --------------------------------------------------------------------------- #
def fixed_time_of_day(commits: list[CommitRecord]) -> float:
    """Fraction of commits sharing the single most common H:M:S, rescaled."""
    if len(commits) < 3:
        return 0.0
    buckets: dict[tuple[int, int, int], int] = {}
    for c in commits:
        key = (c.timestamp.hour, c.timestamp.minute, c.timestamp.second)
        buckets[key] = buckets.get(key, 0) + 1
    modal_fraction = max(buckets.values()) / len(commits)
    return _rescale(modal_fraction, _TIME_BASELINE)


def interval_regularity(commits: list[CommitRecord]) -> float:
    """Suspicion from unnaturally even spacing. Needs >= 5 commits to mean much.

    Uses the coefficient of variation (std/mean) of inter-commit gaps: real work
    is bursty (cv >= ~1); machine-generated cadence is near-constant (cv -> 0).
    """
    if len(commits) < 5:
        return 0.0
    times = sorted(c.timestamp for c in commits)
    gaps = [(b - a).total_seconds() for a, b in zip(times, times[1:])]
    gaps = [g for g in gaps if g > 0]
    if len(gaps) < 4:
        return 0.0
    mean = statistics.mean(gaps)
    if mean == 0:
        return 1.0
    cv = statistics.pstdev(gaps) / mean
    # cv >= 1.0 → 0 suspicion; cv <= 0.2 → full suspicion; linear between.
    return _clamp((1.0 - cv) / (1.0 - 0.2))


def message_quality(commits: list[CommitRecord]) -> float:
    """Blend of generic-message and duplicate-message fractions (merges excluded)."""
    msgs = [
        c.message.strip().lower()
        for c in commits
        if c.message.strip() and not c.message.lstrip().lower().startswith("merge ")
    ]
    if len(msgs) < 3:
        return 0.0
    firsts = [m.splitlines()[0].strip() for m in msgs]
    generic_fraction = sum(1 for m in firsts if m in _GENERIC_MESSAGES) / len(firsts)
    duplicate_fraction = 1.0 - (len(set(firsts)) / len(firsts))
    return _clamp(0.5 * generic_fraction + 0.5 * duplicate_fraction)


def timestamp_collisions(commits: list[CommitRecord]) -> float:
    """Fraction of commits that share an exact timestamp with another, rescaled."""
    if len(commits) < 3:
        return 0.0
    seen: dict[float, int] = {}
    for c in commits:
        key = c.timestamp.timestamp()
        seen[key] = seen.get(key, 0) + 1
    colliding = sum(n for n in seen.values() if n > 1)
    return _rescale(colliding / len(commits), _COLLISION_BASELINE)


def confidence(commit_count: int) -> float:
    """0 at no history, 1.0 once we have MIN_RELIABLE_COMMITS commits."""
    return _clamp(commit_count / MIN_RELIABLE_COMMITS)


# --------------------------------------------------------------------------- #
# Aggregate                                                                    #
# --------------------------------------------------------------------------- #
@dataclass
class CommitForensics:
    score: float  # confidence-damped suspicion in [0, 1]
    raw_suspicion: float
    confidence: float
    components: dict[str, float]
    evidence: list[EvidenceItem] = field(default_factory=list)


_COMPONENT_LABELS = {
    "fixed_time_of_day": "commits cluster at one fixed time of day",
    "interval_regularity": "commits are unnaturally evenly spaced",
    "message_quality": "commit messages are generic or duplicated",
    "timestamp_collisions": "many commits share an exact timestamp",
}


def analyze_commits(commits: list[CommitRecord]) -> CommitForensics:
    components = {
        "fixed_time_of_day": fixed_time_of_day(commits),
        "interval_regularity": interval_regularity(commits),
        "message_quality": message_quality(commits),
        "timestamp_collisions": timestamp_collisions(commits),
    }
    raw = (
        _W_FIXED_TIME * components["fixed_time_of_day"]
        + _W_REGULARITY * components["interval_regularity"]
        + _W_MESSAGE * components["message_quality"]
        + _W_COLLISION * components["timestamp_collisions"]
    )
    conf = confidence(len(commits))
    score = round(_clamp(raw * conf), 4)

    evidence: list[EvidenceItem] = []
    for name, value in components.items():
        if value >= 0.4:  # only surface the components that actually fired
            evidence.append(
                EvidenceItem(
                    id=f"commit_{name}",
                    type=EvidenceType.COMMIT_ANOMALY,
                    feeds=SubScore.COMMIT_FORENSICS,
                    summary=f"{_COMPONENT_LABELS[name]} (signal {value:.2f})",
                    detail={"component": name, "value": round(value, 4), "commit_count": len(commits)},
                    confidence=round(conf, 4),
                )
            )
    return CommitForensics(
        score=score,
        raw_suspicion=round(raw, 4),
        confidence=round(conf, 4),
        components={k: round(v, 4) for k, v in components.items()},
        evidence=evidence,
    )
