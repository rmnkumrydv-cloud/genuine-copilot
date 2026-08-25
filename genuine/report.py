"""Template-engine report generator (spec §6.7 fallback path).

Produces a defensible, plain-English report from ``EvidenceItem``s with **zero
LLM calls**. The Gate-5 RAG explainer is an *upgrade* to this text, never a
replacement for the judgment — this function existing is the proof that the
LLM isn't load-bearing for the verdict.
"""

from __future__ import annotations

from .models import RepoAnalysis, ScoreResult, Verdict

_VERDICT_HEADLINE = {
    Verdict.CLEAN: "CLEAN — no strong signals of copying or fabricated history.",
    Verdict.FLAGGED: "FLAGGED — one or more strong authenticity signals fired.",
    Verdict.INSUFFICIENT_SIGNAL: (
        "INSUFFICIENT SIGNAL — too little history/coverage to judge confidently."
    ),
    Verdict.NEEDS_HUMAN_REVIEW: (
        "NEEDS HUMAN REVIEW — borderline confidence; routed to the review queue "
        "with evidence pre-assembled."
    ),
}


def render_template_report(analysis: RepoAnalysis, score: ScoreResult) -> str:
    lines: list[str] = []
    name = f"{analysis.owner}/{analysis.repo_name}".strip("/") or analysis.repo_url
    lines.append(f"Authenticity report for {name}")
    lines.append("=" * 60)
    lines.append(_VERDICT_HEADLINE[score.verdict])
    lines.append("")
    lines.append(f"Composite suspicion score: {score.composite_score:.2f} "
                 f"(flagged at 0.65; higher = more likely inauthentic)")
    lines.append("")
    lines.append("Sub-scores (each 0=authentic .. 1=suspicious):")
    for name_, val in score.sub_scores().items():
        lines.append(f"  - {name_:<20} {val:.2f}")
    lines.append("")
    lines.append(
        f"Coverage: {score.coverage_ratio:.0%} of includable logic "
        f"({analysis.compared_loc}/{analysis.total_loc} LOC) was deep-compared; "
        f"{score.commit_count} commits analyzed."
    )
    lines.append("")

    if score.evidence:
        lines.append(f"Evidence ({len(score.evidence)} item(s)):")
        for ev in sorted(score.evidence, key=lambda e: -e.confidence):
            lines.append(f"  [{ev.id}] ({ev.feeds.value}, confidence {ev.confidence:.2f})")
            lines.append(f"      {ev.summary}")
    else:
        lines.append("Evidence: none of the deterministic signals fired.")

    lines.append("")
    if score.verdict == Verdict.NEEDS_HUMAN_REVIEW:
        lines.append(
            "Next step: a human reviewer resolves this item. The evidence above is "
            "pre-assembled to shrink review time."
        )
    elif score.verdict == Verdict.INSUFFICIENT_SIGNAL:
        lines.append(
            "Next step: request more history or a larger sample before judging — "
            "this is intentionally NOT an accusation."
        )
    lines.append("")
    lines.append("Report generated deterministically (no LLM). — Genuine")
    return "\n".join(lines)
