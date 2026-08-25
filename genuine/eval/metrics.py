"""Evaluation metrics (spec §8.3): detection quality + the triage headline.

Two framings, both reported, because a hiring-integrity tool lives and dies on
the difference:

* **Detection** — treat ``flagged`` as the positive prediction and measure
  precision / recall / false-positive rate against ground truth. The
  false-positive rate (a *genuine* repo flagged) is the number that matters most:
  falsely accusing a real builder is the expensive error.
* **Triage** — the honest pitch line (§8.3): what fraction resolves automatically
  (``clean`` / ``flagged``) vs. lands in the ``needs_human_review`` queue vs.
  ``insufficient_signal``. Plus an explicitly-assumption-based estimate of
  reviewer time saved, so the number on screen is reproducible and labelled.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..models import Verdict


def _safe_div(num: float, den: float) -> float:
    return num / den if den else 0.0


@dataclass
class ConfusionMatrix:
    """Positive class = inauthentic. Predicted positive = verdict ``flagged``."""

    tp: int = 0  # inauthentic, flagged            (caught)
    fp: int = 0  # authentic, flagged              (false accusation — the costly one)
    tn: int = 0  # authentic, not flagged          (correctly cleared)
    fn: int = 0  # inauthentic, not flagged        (missed / sent to review)

    @property
    def total(self) -> int:
        return self.tp + self.fp + self.tn + self.fn

    @property
    def precision(self) -> float:
        return _safe_div(self.tp, self.tp + self.fp)

    @property
    def recall(self) -> float:
        return _safe_div(self.tp, self.tp + self.fn)

    @property
    def f1(self) -> float:
        p, r = self.precision, self.recall
        return _safe_div(2 * p * r, p + r)

    @property
    def false_positive_rate(self) -> float:
        return _safe_div(self.fp, self.fp + self.tn)

    @property
    def accuracy(self) -> float:
        return _safe_div(self.tp + self.tn, self.total)

    def as_dict(self) -> dict:
        return {
            "tp": self.tp, "fp": self.fp, "tn": self.tn, "fn": self.fn,
            "precision": round(self.precision, 4),
            "recall": round(self.recall, 4),
            "f1": round(self.f1, 4),
            "false_positive_rate": round(self.false_positive_rate, 4),
            "accuracy": round(self.accuracy, 4),
        }


def confusion_from(pairs: list[tuple[bool, Verdict]]) -> ConfusionMatrix:
    """Build the matrix from ``(authentic, verdict)`` pairs.

    ``flagged`` is the only auto-positive; every other verdict (clean,
    needs_human_review, insufficient_signal) is "not auto-flagged". A missed
    inauthentic repo that lands in the review queue is a false negative *for the
    auto-flag metric* — but it is still caught by a human, which the triage
    numbers below make explicit.
    """
    m = ConfusionMatrix()
    for authentic, verdict in pairs:
        flagged = verdict == Verdict.FLAGGED
        if not authentic and flagged:
            m.tp += 1
        elif authentic and flagged:
            m.fp += 1
        elif authentic and not flagged:
            m.tn += 1
        else:
            m.fn += 1
    return m


@dataclass
class TriageStats:
    total: int = 0
    auto_resolved: int = 0  # clean or flagged — no human step
    review_queue: int = 0  # needs_human_review — the only slice a person touches
    insufficient: int = 0  # thin evidence — parked, not judged

    # Detection completeness: inauthentic repos caught either by an auto-flag or
    # by being routed to a human. Distinct from recall, which counts auto-flags
    # only; this is the fraction that did NOT slip through as clean.
    inauthentic_total: int = 0
    inauthentic_caught: int = 0  # flagged OR queued for review

    @property
    def auto_resolved_pct(self) -> float:
        return _safe_div(self.auto_resolved, self.total)

    @property
    def review_queue_pct(self) -> float:
        return _safe_div(self.review_queue, self.total)

    @property
    def insufficient_pct(self) -> float:
        return _safe_div(self.insufficient, self.total)

    @property
    def detection_rate(self) -> float:
        return _safe_div(self.inauthentic_caught, self.inauthentic_total)

    def as_dict(self) -> dict:
        return {
            "total": self.total,
            "auto_resolved": self.auto_resolved,
            "review_queue": self.review_queue,
            "insufficient": self.insufficient,
            "auto_resolved_pct": round(self.auto_resolved_pct, 4),
            "review_queue_pct": round(self.review_queue_pct, 4),
            "insufficient_pct": round(self.insufficient_pct, 4),
            "detection_rate": round(self.detection_rate, 4),
        }


def triage_from(pairs: list[tuple[bool, Verdict]]) -> TriageStats:
    t = TriageStats(total=len(pairs))
    for authentic, verdict in pairs:
        if verdict in (Verdict.CLEAN, Verdict.FLAGGED):
            t.auto_resolved += 1
        elif verdict == Verdict.NEEDS_HUMAN_REVIEW:
            t.review_queue += 1
        else:  # INSUFFICIENT_SIGNAL
            t.insufficient += 1
        if not authentic:
            t.inauthentic_total += 1
            if verdict in (Verdict.FLAGGED, Verdict.NEEDS_HUMAN_REVIEW):
                t.inauthentic_caught += 1
    return t


# --------------------------------------------------------------------------- #
# Reviewer-time-saved estimate (spec §8.3) — assumption-based, clearly labeled #
# --------------------------------------------------------------------------- #
# Defaults are PLACEHOLDER assumptions, not measurements. Replace with a real
# informal timing test (time yourself reviewing one repo cold vs. one with the
# evidence pre-assembled) before quoting these numbers in the pitch.
COLD_REVIEW_MIN = 12.0  # minutes to vet a repo cold, no tooling
GLANCE_MIN = 1.0  # minutes to sanity-check an auto-resolved / parked verdict
ASSISTED_REVIEW_MIN = 4.0  # minutes on a queued item with evidence pre-assembled


def reviewer_time_saved(
    triage: TriageStats,
    *,
    cold_review_min: float = COLD_REVIEW_MIN,
    glance_min: float = GLANCE_MIN,
    assisted_review_min: float = ASSISTED_REVIEW_MIN,
) -> dict:
    """Estimate reviewer minutes with vs. without the tool over ``triage.total``.

    Baseline: a human vets every repo cold. With the tool: auto-resolved and
    insufficient verdicts get a quick glance, only the review queue gets a full
    (evidence-assisted) look.
    """
    n = triage.total
    baseline = n * cold_review_min
    with_tool = (
        (triage.auto_resolved + triage.insufficient) * glance_min
        + triage.review_queue * assisted_review_min
    )
    saved = baseline - with_tool
    return {
        "assumptions": {
            "cold_review_min": cold_review_min,
            "glance_min": glance_min,
            "assisted_review_min": assisted_review_min,
            "note": "PLACEHOLDER — replace with a measured timing test (§8.3).",
        },
        "baseline_min": round(baseline, 1),
        "with_tool_min": round(with_tool, 1),
        "minutes_saved": round(saved, 1),
        "pct_saved": round(_safe_div(saved, baseline), 4),
    }
