"""Data model for Genuine (spec §5).

Direction convention — READ THIS FIRST
--------------------------------------
Every sub-score in :class:`ScoreResult` is a **suspicion** score in ``[0.0, 1.0]``
where **higher means more likely inauthentic**. This resolves the ambiguity in
the spec (is a high ``commit_forensics_score`` good or bad?) so the aggregator is
a plain weighted sum:

    composite = Σ weightᵢ · sub_scoreᵢ        (weights sum to 1.0)

and the verdict thresholds read naturally: ``composite >= 0.65 → flagged``.

So concretely:
* ``clone_similarity_score``   high  → lots of copied code.
* ``registry_match_score``     high  → near-duplicate of a past submission.
* ``commit_forensics_score``   high  → the history looks fabricated/dumped.
* ``readme_consistency_score`` high  → README claims contradict the code.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field


# --------------------------------------------------------------------------- #
# Enums                                                                        #
# --------------------------------------------------------------------------- #
class Verdict(str, Enum):
    CLEAN = "clean"
    FLAGGED = "flagged"
    INSUFFICIENT_SIGNAL = "insufficient_signal"
    NEEDS_HUMAN_REVIEW = "needs_human_review"


class ClaimType(str, Enum):
    TECH_STACK = "tech_stack"
    FEATURE = "feature"
    SETUP_ENV = "setup_env"


class VerificationStatus(str, Enum):
    VERIFIED = "verified"
    UNVERIFIED = "unverified"
    CONTRADICTED = "contradicted"


class DirectionConfidence(str, Enum):
    TARGET_LIKELY_COPIED = "target_likely_copied"
    UNCLEAR_DIRECTION = "unclear_direction"
    CANDIDATE_LIKELY_COPIED = "candidate_likely_copied"


class EvidenceType(str, Enum):
    CLONE_MATCH = "clone_match"
    README_CONTRADICTION = "readme_contradiction"
    COMMIT_ANOMALY = "commit_anomaly"
    REGISTRY_MATCH = "registry_match"


class SubScore(str, Enum):
    """Which weighted channel an :class:`EvidenceItem` feeds."""

    CLONE_SIMILARITY = "clone_similarity"
    README_CONSISTENCY = "readme_consistency"
    COMMIT_FORENSICS = "commit_forensics"
    REGISTRY_MATCH = "registry_match"


# --------------------------------------------------------------------------- #
# Ingestion records                                                            #
# --------------------------------------------------------------------------- #
class DiffStats(BaseModel):
    additions: int = 0
    deletions: int = 0
    files_changed: int = 0


class CommitRecord(BaseModel):
    sha: str
    timestamp: datetime
    message: str
    author_email: str = ""
    diff_stats: DiffStats = Field(default_factory=DiffStats)
    complexity_delta: float = 0.0


class FileRecord(BaseModel):
    path: str
    loc: int = 0
    language: str = "unknown"
    import_centrality: float = 0.0  # normalized: fraction of repo files importing this
    significance_rank: int = 0  # 1 = most significant; 0 = unranked
    significance_score: float = 0.0
    excluded: bool = False  # vendor / generated / test / lockfile
    exclude_reason: str = ""


# --------------------------------------------------------------------------- #
# Signal outputs                                                               #
# --------------------------------------------------------------------------- #
class MatchedFile(BaseModel):
    file: str
    candidate_file: str = ""
    similarity: float = 0.0
    matched_span: list[int] = Field(default_factory=lambda: [0, 0])


class CloneMatch(BaseModel):
    candidate_repo: str
    candidate_created_at: Optional[datetime] = None  # for temporal-direction check
    matched_files: list[MatchedFile] = Field(default_factory=list)
    logic_similarity: float = 0.0  # function bodies (tokens/identifiers/literals)
    structural_similarity: float = 0.0  # AST skeleton (layout/signatures)
    direction_confidence: DirectionConfidence = DirectionConfidence.UNCLEAR_DIRECTION
    self_match_excluded: bool = False


class ReadmeClaim(BaseModel):
    claim_text: str
    claim_type: ClaimType
    verification_status: VerificationStatus = VerificationStatus.UNVERIFIED
    evidence_ref: Optional[str] = None


class EvidenceItem(BaseModel):
    id: str
    type: EvidenceType
    feeds: SubScore  # which weighted channel this evidence contributed to
    summary: str = ""  # one human-readable line, safe to render in the UI
    detail: dict[str, Any] = Field(default_factory=dict)
    confidence: float = 0.0


class InterviewProbe(BaseModel):
    question: str
    targets_evidence_id: str


class AIOpinion(BaseModel):
    """UI-only advisory note for the human review queue (spec §6.8).

    Structurally never an input to scoring: the aggregator's signature does not
    accept it. Same input boundary as the explainer — ScoreResult + retrieved
    evidence chunks only, never raw repo content (closes prompt-injection).
    """

    review_id: str
    summary: str
    label: str = "advisory_only"  # hardcoded — cannot be mistaken for a verdict
    source: str = "ScoreResult + retrieved evidence chunks"


# --------------------------------------------------------------------------- #
# Aggregate result                                                             #
# --------------------------------------------------------------------------- #
class ScoreResult(BaseModel):
    # All four are SUSPICION scores in [0, 1] — higher = more inauthentic.
    commit_forensics_score: float = 0.0
    clone_similarity_score: float = 0.0
    readme_consistency_score: float = 0.0
    registry_match_score: float = 0.0

    composite_score: float = 0.0
    coverage_ratio: float = 0.0
    commit_count: int = 0

    verdict: Verdict = Verdict.INSUFFICIENT_SIGNAL
    evidence: list[EvidenceItem] = Field(default_factory=list)

    # NOTE: ai_opinion is intentionally NOT a field here. It is UI-only and lives
    # on the API response, never on the object the aggregator produces or reads.

    def sub_scores(self) -> dict[str, float]:
        return {
            SubScore.CLONE_SIMILARITY.value: self.clone_similarity_score,
            SubScore.README_CONSISTENCY.value: self.readme_consistency_score,
            SubScore.COMMIT_FORENSICS.value: self.commit_forensics_score,
            SubScore.REGISTRY_MATCH.value: self.registry_match_score,
        }


class RepoAnalysis(BaseModel):
    repo_url: str
    owner: str = ""
    repo_name: str = ""
    default_branch: str = "main"
    ingested_at: datetime
    repo_created_at: Optional[datetime] = None

    commits: list[CommitRecord] = Field(default_factory=list)
    files: list[FileRecord] = Field(default_factory=list)
    readme_text: str = ""
    readme_claims: list[ReadmeClaim] = Field(default_factory=list)

    total_loc: int = 0  # includable LOC (after vendor/test/generated exclusion)
    compared_loc: int = 0  # LOC actually sent to expensive comparison (top-K)
    coverage_ratio: float = 0.0  # compared_loc / total_loc
    fingerprint: list[int] = Field(default_factory=list)  # MinHash signature

    def significant_files(self) -> list[FileRecord]:
        """Ranked, non-excluded files (most significant first)."""
        ranked = [f for f in self.files if not f.excluded and f.significance_rank > 0]
        return sorted(ranked, key=lambda f: f.significance_rank)
