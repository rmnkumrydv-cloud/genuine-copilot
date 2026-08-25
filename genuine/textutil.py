"""Small, dependency-free text/token helpers shared across signals.

The heavyweight, Python-aware normalization (AST skeletons, token streams for
clone detection) lives in :mod:`genuine.signals.similarity`. This module only
holds the language-agnostic pieces the fingerprinter and fallbacks need.
"""

from __future__ import annotations

import re

_WORD = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")


def word_tokens(text: str) -> list[str]:
    """Identifier-ish tokens, lowercased. Language-agnostic, deterministic."""
    return [t.lower() for t in _WORD.findall(text)]


def shingles(tokens: list[str], k: int = 5) -> set[str]:
    """Overlapping k-grams over a token list, as joined strings.

    k-grams (not single tokens) are what make MinHash discriminative: any two
    codebases share plenty of individual identifiers, but sharing long ordered
    runs of them is the actual copy signal.
    """
    if k <= 1 or len(tokens) < k:
        return {" ".join(tokens)} if tokens else set()
    return {" ".join(tokens[i : i + k]) for i in range(len(tokens) - k + 1)}
