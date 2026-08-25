"""End-to-end analysis pipeline (spec §3 flow).

Wires ingestion → the four deterministic signals → the rules.yaml aggregator →
registry update, and assembles the final API-facing payload. This is the
"confident verdict" path; the RAG/LLM explainer (Gate 5) layers on top of the
``ScoreResult`` this produces without changing any judgment.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from .ingestion.repo import ingest
from .models import RepoAnalysis, ScoreResult
from .report import render_template_report
from .scoring import Rulebook, aggregate
from .signals import analyze_commits, analyze_readme
from .signals.clone import CandidateRepo, detect_clones
from .signals.registry import check as registry_check
from .signals.registry import register as registry_register
from .store import init_schema


@dataclass
class AnalysisResult:
    analysis: RepoAnalysis
    score: ScoreResult
    report_text: str
    self_excluded: list[str] = field(default_factory=list)
    matcher_name: str = ""

    def to_payload(self) -> dict:
        """API-facing dict: verdict + sub-scores + evidence + coverage + report."""
        return {
            "repo_url": self.analysis.repo_url,
            "owner": self.analysis.owner,
            "repo_name": self.analysis.repo_name,
            "verdict": self.score.verdict.value,
            "composite_score": self.score.composite_score,
            "sub_scores": self.score.sub_scores(),
            "coverage_ratio": self.score.coverage_ratio,
            "commit_count": self.score.commit_count,
            "total_loc": self.analysis.total_loc,
            "compared_loc": self.analysis.compared_loc,
            "evidence": [e.model_dump() for e in self.score.evidence],
            "readme_claims": [c.model_dump() for c in self.analysis.readme_claims],
            "self_excluded_candidates": self.self_excluded,
            "matcher": self.matcher_name,
            "report_text": self.report_text,
        }


def _texts_for(analysis: RepoAnalysis, cache_root: Path) -> dict[str, str]:
    """Re-read the significant files' source from the working copy on disk.

    Ingestion doesn't retain full source on the model (keeps RepoAnalysis JSON
    small); the pipeline re-reads only the ranked files it actually compares.
    """
    root = Path(analysis.repo_url)
    if not root.is_dir():
        # remote repo -> it was cloned into the cache during ingest()
        from .ingestion.github import parse_repo_url

        ref = parse_repo_url(analysis.repo_url)
        if ref:
            root = cache_root / ref.host / ref.owner / ref.name
    texts: dict[str, str] = {}
    for fr in analysis.significant_files():
        fp = root / fr.path
        try:
            texts[fr.path] = fp.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
    return texts


def analyze(
    url_or_path: str,
    *,
    db_path: str | Path,
    cache_root: Path,
    candidates: Optional[list[CandidateRepo]] = None,
    token: str = "",
    rulebook: Optional[Rulebook] = None,
    register_in_registry: bool = True,
    top_k: int = 40,
) -> AnalysisResult:
    init_schema(db_path)
    rb = rulebook or Rulebook.load()

    analysis = ingest(url_or_path, cache_root=cache_root, token=token, top_k=top_k)
    texts = _texts_for(analysis, cache_root)

    # --- deterministic signals ---
    commit = analyze_commits(analysis.commits)
    clone = detect_clones(analysis, texts, candidates or [])
    readme = analyze_readme(analysis.readme_text, analysis.files, texts)
    analysis.readme_claims = readme.claims

    # registry: CHECK before REGISTER, so a repo never matches itself (§8.4-7)
    registry = registry_check(db_path, analysis)

    evidence = [*clone.evidence, *readme.evidence, *commit.evidence, *registry.evidence]

    score = aggregate(
        clone_similarity=clone.score,
        readme_consistency=readme.score,
        commit_forensics=commit.score,
        registry_match=registry.score,
        coverage_ratio=analysis.coverage_ratio,
        commit_count=len(analysis.commits),
        evidence=evidence,
        rulebook=rb,
    )

    if register_in_registry:
        registry_register(db_path, analysis)

    report = render_template_report(analysis, score)
    return AnalysisResult(
        analysis=analysis,
        score=score,
        report_text=report,
        self_excluded=clone.self_excluded,
        matcher_name="stdlib-ast",
    )
