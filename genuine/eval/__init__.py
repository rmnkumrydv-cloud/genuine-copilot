"""Evaluation harness for Genuine (spec §8.3, Gate 7).

A deterministic, offline, labeled corpus + a harness that runs the full pipeline
over it and reports detection metrics (precision / recall / false-positive rate)
and the triage headline (auto-resolved vs. review-queue), honoring the
tuning/held-out split so reported numbers can't leak from the tuning set.
"""

from __future__ import annotations

from .dataset import (
    CORPUS,
    HELDOUT,
    TUNING,
    LabeledRepo,
    assert_no_leakage,
    for_split,
    heldout_set,
    tuning_set,
)
from .harness import EvalReport, RepoOutcome, evaluate_repo, run_eval
from .metrics import ConfusionMatrix, TriageStats, reviewer_time_saved

__all__ = [
    "CORPUS",
    "TUNING",
    "HELDOUT",
    "LabeledRepo",
    "for_split",
    "tuning_set",
    "heldout_set",
    "assert_no_leakage",
    "run_eval",
    "evaluate_repo",
    "EvalReport",
    "RepoOutcome",
    "ConfusionMatrix",
    "TriageStats",
    "reviewer_time_saved",
]
