"""Scoring aggregator + verdict logic (spec §6.6).

The rulebook is *data* (``rules.yaml``), loaded at runtime — changing a weight or
threshold changes the verdict with no code change. That's the property the pitch
claims and ``tests/test_scoring.py`` enforces.

Structural neuro-symbolic boundary (spec §6.8): :func:`aggregate` has no
parameter for an LLM opinion. It is not "we promise not to pass it" — the
function simply cannot receive it. AI output physically cannot influence a score.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml

from ..models import EvidenceItem, ScoreResult, Verdict

DEFAULT_RULES_PATH = Path(__file__).with_name("rules.yaml")


@dataclass
class Rulebook:
    weights: dict[str, float]
    flagged: float
    review_low: float
    min_commits: int
    min_coverage: float
    critical: dict[str, float]

    @classmethod
    def load(cls, path: str | Path = DEFAULT_RULES_PATH) -> "Rulebook":
        data = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
        th = data["thresholds"]
        insuf = data["insufficient_signal"]
        return cls(
            weights=dict(data["weights"]),
            flagged=float(th["flagged"]),
            review_low=float(th["review_low"]),
            min_commits=int(insuf["min_commits"]),
            min_coverage=float(insuf["min_coverage"]),
            critical=dict(data.get("critical_signals", {})),
        )


def composite_score(sub_scores: dict[str, float], rulebook: Rulebook) -> float:
    """Weighted sum, normalized by total weight so the result stays in [0, 1]
    even if a custom rulebook's weights don't sum to exactly 1.0.
    """
    total_w = sum(rulebook.weights.values()) or 1.0
    acc = sum(rulebook.weights.get(k, 0.0) * sub_scores.get(k, 0.0) for k in rulebook.weights)
    return round(acc / total_w, 4)


def decide_verdict(
    composite: float,
    coverage_ratio: float,
    commit_count: int,
    rulebook: Rulebook,
    sub_scores: dict[str, float] | None = None,
) -> Verdict:
    """The verdict logic. Order matters — see rules.yaml comments.

    A critical single-signal override (e.g. a verbatim clone) takes top
    precedence: it flags on its own even over thin coverage/history, which is
    exactly the fabricated-timeline-around-copied-code case (§8.4-3).
    """
    sub_scores = sub_scores or {}
    for name, threshold in rulebook.critical.items():
        if sub_scores.get(name, 0.0) >= threshold:
            return Verdict.FLAGGED

    thin = coverage_ratio < rulebook.min_coverage or commit_count < rulebook.min_commits
    if thin and composite < rulebook.flagged:
        return Verdict.INSUFFICIENT_SIGNAL
    if composite >= rulebook.flagged:
        return Verdict.FLAGGED
    if composite >= rulebook.review_low:
        return Verdict.NEEDS_HUMAN_REVIEW
    return Verdict.CLEAN


def aggregate(
    *,
    clone_similarity: float,
    readme_consistency: float,
    commit_forensics: float,
    registry_match: float,
    coverage_ratio: float,
    commit_count: int,
    evidence: list[EvidenceItem] | None = None,
    rulebook: Rulebook | None = None,
) -> ScoreResult:
    """Combine the four suspicion sub-scores into a verdict.

    NOTE the signature: there is no ``ai_opinion`` / ``llm_*`` parameter, by
    design. This is the enforced boundary, not a promise.
    """
    rb = rulebook or Rulebook.load()
    sub = {
        "clone_similarity": clone_similarity,
        "readme_consistency": readme_consistency,
        "commit_forensics": commit_forensics,
        "registry_match": registry_match,
    }
    composite = composite_score(sub, rb)
    verdict = decide_verdict(composite, coverage_ratio, commit_count, rb, sub_scores=sub)
    return ScoreResult(
        clone_similarity_score=round(clone_similarity, 4),
        readme_consistency_score=round(readme_consistency, 4),
        commit_forensics_score=round(commit_forensics, 4),
        registry_match_score=round(registry_match, 4),
        composite_score=composite,
        coverage_ratio=round(coverage_ratio, 4),
        commit_count=commit_count,
        verdict=verdict,
        evidence=evidence or [],
    )
