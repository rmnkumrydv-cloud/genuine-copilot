"""Declarative scoring (spec §6.6)."""

from __future__ import annotations

from .aggregator import (
    DEFAULT_RULES_PATH,
    Rulebook,
    aggregate,
    composite_score,
    decide_verdict,
)

__all__ = [
    "Rulebook",
    "aggregate",
    "composite_score",
    "decide_verdict",
    "DEFAULT_RULES_PATH",
]
