"""Gate-5 explainer + interview-prep generator.

One Groq call turns a **finished** :class:`~genuine.models.ScoreResult` into two
advisory artifacts for the human reviewer:

* an :class:`~genuine.models.AIOpinion` — plain-language prose about what the
  verdict and evidence mean;
* a list of :class:`~genuine.models.InterviewProbe` — questions that let an
  honest author demonstrate they understand and wrote the code.

The input boundary is enforced by :func:`_context`: the model receives the
verdict, the sub-scores, coverage, and the human-safe evidence *summaries* — and
nothing else. It never sees raw source or README text, so a hostile repo cannot
smuggle instructions into the prompt, and the model cannot "peek" at code to
second-guess the deterministic result. The output is prose; scoring has already
happened and has no channel to receive it.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any, Optional

from ..models import AIOpinion, InterviewProbe, ScoreResult
from .client import GroqChat

# --------------------------------------------------------------------------- #
# Prompt                                                                       #
# --------------------------------------------------------------------------- #
_SYSTEM = (
    "You assist a human reviewer who is judging whether a software project is the "
    "candidate's own authentic work. A deterministic, auditable system has ALREADY "
    "produced the FINAL verdict and scores shown below.\n"
    "\n"
    "These are FINAL. Never dispute, recompute, second-guess, or override them. Your "
    "only job is to explain them and to help the reviewer verify authorship in person.\n"
    "\n"
    "Return a single JSON object with EXACTLY these keys:\n"
    '  "explanation": a neutral, plain-language summary (2-4 short sentences) of what '
    "the verdict and evidence mean and what the reviewer should check. If the verdict "
    'is "insufficient_signal", state clearly this means NOT ENOUGH DATA — it is not an '
    "accusation.\n"
    '  "interview_questions": an array of 3-6 objects, each {"question": string, '
    '"targets": short string}, that let an honest author show they understand and wrote '
    "this code. If a copying/duplication signal fired, include questions asking them to "
    "re-derive or explain that specific code from scratch. Never accuse.\n"
    "\n"
    "Use ONLY the facts provided below. Do not invent files, matches, or details."
)


# --------------------------------------------------------------------------- #
# Result container                                                             #
# --------------------------------------------------------------------------- #
@dataclass
class LLMReview:
    """What the LLM layer adds to a finished analysis. Both fields degrade to
    empty when no key is configured or the call fails."""

    ai_opinion: Optional[AIOpinion] = None
    interview_probes: list[InterviewProbe] = field(default_factory=list)

    @property
    def available(self) -> bool:
        return self.ai_opinion is not None or bool(self.interview_probes)


# --------------------------------------------------------------------------- #
# The input boundary — the ONLY thing the model sees                           #
# --------------------------------------------------------------------------- #
def _context(score: ScoreResult, repo_name: str) -> str:
    """Render the deterministic result as text. Scores + safe evidence summaries
    only — never raw source or README (see module docstring)."""
    lines = [
        f"Repository: {repo_name or '(unnamed)'}",
        f"Final verdict: {score.verdict.value}",
        f"Composite suspicion score: {score.composite_score:.2f} "
        "(0 = authentic, 1 = suspicious; flagged at 0.65).",
        f"Analysis coverage: {score.coverage_ratio:.0%} of significant code was "
        f"deep-compared; {score.commit_count} commits analyzed.",
        "Sub-scores (0 = clean .. 1 = suspicious):",
    ]
    for name, value in score.sub_scores().items():
        lines.append(f"  - {name}: {value:.2f}")

    if score.evidence:
        lines.append("Evidence that fired:")
        for e in sorted(score.evidence, key=lambda e: e.confidence, reverse=True):
            lines.append(f"  - [{e.feeds.value}, confidence {e.confidence:.2f}] {e.summary}")
    else:
        lines.append("Evidence: no deterministic signal fired.")
    return "\n".join(lines)


def _review_id(score: ScoreResult, repo_name: str) -> str:
    """Stable, deterministic id (no uuid/clock needed — reproducible across runs)."""
    seed = f"{repo_name}|{score.verdict.value}|{score.composite_score:.4f}"
    return "rev_" + hashlib.sha1(seed.encode("utf-8")).hexdigest()[:12]


def _parse_probes(data: Any) -> list[InterviewProbe]:
    """Map the model's ``interview_questions`` array to InterviewProbe, skipping
    anything malformed. Defensive: the LLM output is untrusted structure."""
    if not isinstance(data, list):
        return []
    probes: list[InterviewProbe] = []
    for item in data:
        if isinstance(item, dict) and str(item.get("question", "")).strip():
            probes.append(
                InterviewProbe(
                    question=str(item["question"]).strip(),
                    targets_evidence_id=str(item.get("targets", "general") or "general").strip(),
                )
            )
    return probes


# --------------------------------------------------------------------------- #
# Public API                                                                   #
# --------------------------------------------------------------------------- #
def is_available(chat: Optional[GroqChat] = None) -> bool:
    """Whether the LLM layer can run (a Groq key is configured)."""
    return (chat or GroqChat()).available


def review(
    score: ScoreResult,
    *,
    repo_name: str = "",
    chat: Optional[GroqChat] = None,
) -> LLMReview:
    """Produce the advisory explanation and interview probes in one call.

    Returns an empty :class:`LLMReview` (no opinion, no probes) when no key is
    configured or the API call fails — the caller keeps the template report.
    """
    chat = chat or GroqChat()
    raw = chat.complete(_SYSTEM, _context(score, repo_name), json_mode=True)
    if not raw:
        return LLMReview()

    explanation = ""
    probes: list[InterviewProbe] = []
    try:
        data = json.loads(raw)
        explanation = str(data.get("explanation", "")).strip()
        probes = _parse_probes(data.get("interview_questions"))
    except (ValueError, AttributeError):
        # Not valid JSON (shouldn't happen in json_mode) — treat the whole
        # response as the explanation rather than losing it.
        explanation = raw.strip()

    opinion = (
        AIOpinion(review_id=_review_id(score, repo_name), summary=explanation)
        if explanation
        else None
    )
    return LLMReview(ai_opinion=opinion, interview_probes=probes)


def explain(
    score: ScoreResult,
    *,
    repo_name: str = "",
    chat: Optional[GroqChat] = None,
) -> Optional[AIOpinion]:
    """Convenience: just the advisory prose (``review(...).ai_opinion``)."""
    return review(score, repo_name=repo_name, chat=chat).ai_opinion
