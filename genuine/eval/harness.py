"""The evaluation harness (spec §8.3, Gate 7).

Materializes each labeled repo into a real, tiny git repository (so the actual
gitpython ingestion + deterministic signals run, not a mock), runs the pipeline
fully offline, and aggregates verdicts into a detection confusion matrix + triage
stats + an assumption-based reviewer-time estimate.

The harness never calls the LLM (``explain=False``) and never writes to the
shared registry (``register_in_registry=False``) — every repo is judged on its
own merits in isolation, so the metrics reflect the clone / README / commit
signals, not cross-repo registry state (which has its own unit tests).
"""

from __future__ import annotations

import tempfile
from contextlib import nullcontext
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from git import Actor, Repo

from ..models import ScoreResult, Verdict
from ..pipeline import analyze
from ..scoring import Rulebook
from ..signals.clone import CandidateRepo
from . import dataset as ds
from .dataset import LabeledRepo
from .metrics import (
    ConfusionMatrix,
    TriageStats,
    confusion_from,
    reviewer_time_saved,
    triage_from,
)

_ACTOR = Actor("Eval Harness", "eval@genuine.local")


def _materialize(repo: LabeledRepo, root: Path) -> Path:
    """Build ``repo`` as a git repository under ``root`` and return its path."""
    root.mkdir(parents=True, exist_ok=True)
    git_repo = Repo.init(root)
    for spec in repo.commits:
        for rel, content in spec.get("files", {}).items():
            fp = root / rel
            fp.parent.mkdir(parents=True, exist_ok=True)
            fp.write_text(content, encoding="utf-8")
            git_repo.index.add([str(fp)])
        date = spec.get("date")
        git_repo.index.commit(
            spec.get("message", "commit"),
            author=_ACTOR, committer=_ACTOR,
            author_date=date, commit_date=date,
        )
    git_repo.close()  # release .git handles promptly (Windows locks open files)
    return root


def _candidates(repo: LabeledRepo) -> list[CandidateRepo]:
    if repo.candidate is None:
        return []
    c = repo.candidate
    return [CandidateRepo(slug=c.slug, owner=c.owner, files=dict(c.files), created_at=c.created_at)]


@dataclass
class RepoOutcome:
    repo_id: str
    category: str
    authentic: bool
    split: str
    verdict: Verdict
    composite_score: float
    sub_scores: dict
    note: str

    @property
    def correct(self) -> bool:
        """Authentic → not flagged; inauthentic → flagged or queued for review."""
        if self.authentic:
            return self.verdict != Verdict.FLAGGED
        return self.verdict in (Verdict.FLAGGED, Verdict.NEEDS_HUMAN_REVIEW)

    def as_dict(self) -> dict:
        return {
            "repo_id": self.repo_id, "category": self.category,
            "authentic": self.authentic, "split": self.split,
            "verdict": self.verdict.value,
            "composite_score": round(self.composite_score, 4),
            "sub_scores": {k: round(v, 4) for k, v in self.sub_scores.items()},
            "correct": self.correct,
        }


def evaluate_repo(
    repo: LabeledRepo, *, work_root: Path, db_path: Path, cache_root: Path,
    rulebook: Optional[Rulebook] = None,
) -> RepoOutcome:
    root = _materialize(repo, work_root / repo.repo_id)
    result = analyze(
        str(root), db_path=db_path, cache_root=cache_root,
        candidates=_candidates(repo), rulebook=rulebook,
        register_in_registry=False, explain=False,
    )
    score: ScoreResult = result.score
    return RepoOutcome(
        repo_id=repo.repo_id, category=repo.category, authentic=repo.authentic,
        split=repo.split, verdict=score.verdict, composite_score=score.composite_score,
        sub_scores=score.sub_scores(), note=repo.note,
    )


@dataclass
class EvalReport:
    split: str
    outcomes: list[RepoOutcome] = field(default_factory=list)
    matrix: ConfusionMatrix = field(default_factory=ConfusionMatrix)
    triage: TriageStats = field(default_factory=TriageStats)
    time_saved: dict = field(default_factory=dict)

    def metrics_dict(self) -> dict:
        return {
            "split": self.split,
            "n": len(self.outcomes),
            "confusion": self.matrix.as_dict(),
            "triage": self.triage.as_dict(),
            "reviewer_time_saved": self.time_saved,
        }

    def to_markdown(self) -> str:
        return _render_markdown(self)


def run_eval(
    split: str = ds.HELDOUT, *, rulebook: Optional[Rulebook] = None,
    workdir: Optional[Path] = None,
) -> EvalReport:
    """Run the pipeline over every repo in ``split`` and aggregate the metrics.

    Pass ``workdir`` to keep the materialized repos around (tests); otherwise a
    temporary directory is used and cleaned up.
    """
    ds.assert_no_leakage()  # refuse to run on a leaky split (§8.4-6)
    repos = ds.for_split(split)

    ctx = (
        nullcontext(str(workdir))
        if workdir is not None
        # SQLite (WAL) + gitpython keep handles briefly past close on Windows;
        # the metrics are computed before teardown, so tolerate cleanup lag.
        else tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
    )
    with ctx as tmp:
        base = Path(tmp)
        db_path = base / "eval.sqlite"
        cache_root = base / "clones"
        cache_root.mkdir(parents=True, exist_ok=True)
        work_root = base / "repos"
        outcomes = [
            evaluate_repo(r, work_root=work_root, db_path=db_path,
                          cache_root=cache_root, rulebook=rulebook)
            for r in repos
        ]

    pairs = [(o.authentic, o.verdict) for o in outcomes]
    triage = triage_from(pairs)
    return EvalReport(
        split=split, outcomes=outcomes,
        matrix=confusion_from(pairs), triage=triage,
        time_saved=reviewer_time_saved(triage),
    )


# --------------------------------------------------------------------------- #
# Markdown artifact                                                            #
# --------------------------------------------------------------------------- #
def _render_markdown(report: EvalReport) -> str:
    m, t, ts = report.matrix, report.triage, report.time_saved
    lines: list[str] = []
    lines.append(f"# Evaluation — `{report.split}` split")
    lines.append("")
    lines.append(
        "> Generated by `genuine eval`. Metrics below come **only** from the "
        f"`{report.split}` split (spec §8.4-6). The corpus is a deterministic, "
        "offline, synthetic labeled set — see the note at the bottom."
    )
    lines.append("")
    lines.append("## Detection (positive class = inauthentic, auto-flag only)")
    lines.append("")
    lines.append("| Metric | Value |")
    lines.append("|---|---|")
    lines.append(f"| Repos evaluated | {m.total} |")
    lines.append(f"| Precision | {m.precision:.3f} |")
    lines.append(f"| Recall (auto-flag) | {m.recall:.3f} |")
    lines.append(f"| F1 | {m.f1:.3f} |")
    lines.append(f"| **False-positive rate** | **{m.false_positive_rate:.3f}** |")
    lines.append(f"| Accuracy | {m.accuracy:.3f} |")
    lines.append(f"| Confusion (tp/fp/tn/fn) | {m.tp} / {m.fp} / {m.tn} / {m.fn} |")
    lines.append("")
    lines.append("## Triage (the pitch headline, §8.3)")
    lines.append("")
    lines.append("| Metric | Value |")
    lines.append("|---|---|")
    lines.append(f"| Auto-resolved (clean/flagged) | {t.auto_resolved}/{t.total} ({t.auto_resolved_pct:.1%}) |")
    lines.append(f"| Review queue (needs_human_review) | {t.review_queue}/{t.total} ({t.review_queue_pct:.1%}) |")
    lines.append(f"| Insufficient signal | {t.insufficient}/{t.total} ({t.insufficient_pct:.1%}) |")
    lines.append(f"| Detection rate (flagged OR queued) | {t.inauthentic_caught}/{t.inauthentic_total} ({t.detection_rate:.1%}) |")
    lines.append("")
    lines.append(
        f"**Reviewer time (estimated):** ~{ts['baseline_min']:.0f} min cold vs. "
        f"~{ts['with_tool_min']:.0f} min with the tool over {t.total} repos "
        f"— **{ts['pct_saved']:.0%} saved**. "
        f"_Assumptions (placeholder, replace with a measured test): cold "
        f"{ts['assumptions']['cold_review_min']:.0f} min/repo, assisted "
        f"{ts['assumptions']['assisted_review_min']:.0f} min/queued, glance "
        f"{ts['assumptions']['glance_min']:.0f} min otherwise._"
    )
    lines.append("")
    lines.append("## Per-repo outcomes")
    lines.append("")
    lines.append("| repo_id | category | verdict | composite | clone | correct |")
    lines.append("|---|---|---|---|---|---|")
    for o in report.outcomes:
        mark = "✓" if o.correct else "✗"
        lines.append(
            f"| `{o.repo_id}` | {o.category} | {o.verdict.value} | "
            f"{o.composite_score:.3f} | {o.sub_scores.get('clone_similarity', 0.0):.3f} | {mark} |"
        )
    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append(
        "**Corpus note.** This is a synthetic, offline, deterministic labeled set "
        "(10 original / 8 copied / 6 faked), split into `tuning` (weights tuned "
        "here) and `heldout` (metrics reported here). It is built from "
        "known-relationship sources so every ground-truth label is unarguable; it "
        "is *not* a sample of real GitHub repos. It validates the scoring "
        "boundary and the §8.4 regression behavior end-to-end; a real-repo "
        "benchmark (and Type-3/4 partial clones) is roadmap."
    )
    lines.append("")
    return "\n".join(lines)
