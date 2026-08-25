"""Repo-level clone detection (spec §6.3, §8.4 cases 2/4/5).

Compares the target's *significant* files against a set of candidate repos and
produces one :class:`CloneMatch` per candidate plus the overall
``clone_similarity`` suspicion score. Three guardrails from the spec live here:

* **self-match exclusion** (§8.4-4) — a repo is never compared against itself or
  another repo from the same owner.
* **temporal direction** (§8.4-5) — a match only raises suspicion of *the target*
  copying when the candidate provably predates it; a newer candidate is heavily
  down-weighted (it may have copied *us*).
* **structure-vs-logic** (§8.4-2) — the score is driven by *logic* similarity, so
  shared boilerplate (high structural, low logic) does not inflate it.

The score is a pure function of file-pair similarities and the direction weight —
no ML, no opinion.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

from ..ingestion.languages import detect_language
from ..models import (
    CloneMatch,
    DirectionConfidence,
    EvidenceItem,
    EvidenceType,
    FileRecord,
    MatchedFile,
    RepoAnalysis,
    SubScore,
)
from .matchers import DEFAULT_MATCHER, CloneMatcher

# A file pair at/above this logic similarity counts as a "strong" match.
STRONG_MATCH = 0.70
# Direction multipliers applied to a candidate's raw suspicion. "Unclear" is only
# a modest discount (we still can't rule out copying); a candidate that provably
# postdates the target is heavily discounted (it likely copied US, not vice versa).
_DIRECTION_WEIGHT = {
    DirectionConfidence.TARGET_LIKELY_COPIED: 1.0,
    DirectionConfidence.UNCLEAR_DIRECTION: 0.85,
    DirectionConfidence.CANDIDATE_LIKELY_COPIED: 0.35,
}


@dataclass
class CandidateRepo:
    """A repo to compare the target against — from the registry, code search, or
    a local fixture. ``created_at`` enables the temporal-direction check.
    """

    slug: str  # "owner/name"
    owner: str
    files: dict[str, str]  # path -> source text
    created_at: Optional[datetime] = None


@dataclass
class CloneResult:
    score: float  # clone_similarity suspicion in [0, 1]
    matches: list[CloneMatch] = field(default_factory=list)
    evidence: list[EvidenceItem] = field(default_factory=list)
    self_excluded: list[str] = field(default_factory=list)


def _direction(
    target_created: Optional[datetime], candidate_created: Optional[datetime]
) -> DirectionConfidence:
    if target_created is None or candidate_created is None:
        return DirectionConfidence.UNCLEAR_DIRECTION
    if candidate_created < target_created:
        return DirectionConfidence.TARGET_LIKELY_COPIED
    if candidate_created > target_created:
        return DirectionConfidence.CANDIDATE_LIKELY_COPIED
    return DirectionConfidence.UNCLEAR_DIRECTION


def _compare_to_candidate(
    target_files: list[FileRecord],
    target_texts: dict[str, str],
    candidate: CandidateRepo,
    target_created: Optional[datetime],
    matcher: CloneMatcher,
) -> tuple[CloneMatch, float]:
    """Compare one candidate. Returns (CloneMatch, direction-weighted suspicion)."""
    direction = _direction(target_created, candidate.created_at)
    matched: list[MatchedFile] = []

    weighted_logic_sum = 0.0
    strong_loc = 0.0
    total_loc = 0.0
    strong_structs: list[float] = []  # structural sim of strongly-matched files

    # Group candidate files by language for same-language comparison only.
    for tf in target_files:
        src = target_texts.get(tf.path)
        if not src:
            continue
        total_loc += tf.loc
        best: Optional[tuple[float, float, str, tuple[int, int]]] = None
        for cpath, csrc in candidate.files.items():
            if detect_language(cpath) != tf.language:
                continue
            cmp = matcher.compare_files(src, csrc, tf.language)
            if best is None or cmp.logic_similarity > best[0]:
                best = (cmp.logic_similarity, cmp.structural_similarity, cpath, cmp.matched_span)
        if best is None:
            continue
        logic, struct, cpath, span = best
        weighted_logic_sum += logic * tf.loc
        if logic >= STRONG_MATCH:
            strong_loc += tf.loc
            strong_structs.append(struct)
            matched.append(
                MatchedFile(
                    file=tf.path,
                    candidate_file=cpath,
                    similarity=round(logic, 4),
                    matched_span=list(span),
                )
            )

    repo_logic = (weighted_logic_sum / total_loc) if total_loc else 0.0
    match_coverage = (strong_loc / total_loc) if total_loc else 0.0
    # Structural similarity averaged over the strongly-matched files, for context
    # in the evidence (it does NOT feed the score — only logic does).
    repo_struct = (sum(strong_structs) / len(strong_structs)) if strong_structs else 0.0
    raw = 0.7 * repo_logic + 0.3 * match_coverage
    weighted = raw * _DIRECTION_WEIGHT[direction]

    clone_match = CloneMatch(
        candidate_repo=candidate.slug,
        candidate_created_at=candidate.created_at,
        matched_files=matched,
        logic_similarity=round(repo_logic, 4),
        structural_similarity=round(repo_struct, 4),
        direction_confidence=direction,
        self_match_excluded=False,
    )
    return clone_match, round(min(1.0, weighted), 4)


def detect_clones(
    target: RepoAnalysis,
    target_texts: dict[str, str],
    candidates: list[CandidateRepo],
    matcher: CloneMatcher = DEFAULT_MATCHER,
) -> CloneResult:
    significant = target.significant_files()
    self_excluded: list[str] = []
    matches: list[CloneMatch] = []
    best_score = 0.0
    best_match: Optional[CloneMatch] = None

    for cand in candidates:
        # Self-match exclusion (§8.4-4): same repo or same owner.
        target_slug = f"{target.owner}/{target.repo_name}" if target.owner else target.repo_name
        if cand.slug == target_slug or (target.owner and cand.owner == target.owner):
            self_excluded.append(cand.slug)
            continue

        clone_match, weighted = _compare_to_candidate(
            significant, target_texts, cand, target.repo_created_at, matcher
        )
        matches.append(clone_match)
        if weighted > best_score:
            best_score = weighted
            best_match = clone_match

    evidence: list[EvidenceItem] = []
    if best_match and best_score >= 0.3:
        evidence.append(
            EvidenceItem(
                id=f"clone_{best_match.candidate_repo.replace('/', '_')}",
                type=EvidenceType.CLONE_MATCH,
                feeds=SubScore.CLONE_SIMILARITY,
                summary=(
                    f"{len(best_match.matched_files)} file(s) closely match "
                    f"{best_match.candidate_repo} "
                    f"(logic {best_match.logic_similarity:.2f}, "
                    f"structural {best_match.structural_similarity:.2f}, "
                    f"direction: {best_match.direction_confidence.value})"
                ),
                detail={
                    "candidate_repo": best_match.candidate_repo,
                    "logic_similarity": best_match.logic_similarity,
                    "structural_similarity": best_match.structural_similarity,
                    "direction_confidence": best_match.direction_confidence.value,
                    "matched_files": [m.model_dump() for m in best_match.matched_files],
                },
                confidence=round(best_score, 4),
            )
        )

    return CloneResult(
        score=round(best_score, 4),
        matches=matches,
        evidence=evidence,
        self_excluded=self_excluded,
    )
