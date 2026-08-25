"""Deterministic README claim extraction (the non-tech half of Gate 4).

Tech-stack claims stay in :mod:`genuine.signals.readme_consistency` because they
drive the *score* and must remain the auditable authority. This module extracts
the softer **feature** and **setup** claims that RAG can *ground* to code —
they're advisory (never fed into the suspicion score), so heuristic extraction
is safe here.

Each :class:`ExtractedClaim` carries the query ``terms`` used to retrieve the
code region that would support it.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from ..models import ClaimType
from .retrieval import tokenize

# Sentences asserting a capability. "uses"/"built with" are deliberately absent:
# those are tech-stack claims, owned by the scoring signal.
_FEATURE_VERB = re.compile(
    r"\b(supports?|enables?|allows?|provides?|generates?|detects?|computes?|"
    r"exports?|imports?|parses?|validates?|handles?|manages?|implements?|"
    r"lets you|can)\b",
    re.IGNORECASE,
)
_BULLET = re.compile(r"^\s*[-*+]\s+(.+?)\s*$")
_HEADING = re.compile(r"^\s*#{1,6}\s")
_FENCE = re.compile(r"^\s*```")
# Setup commands worth grounding (does the repo actually support them?).
_SETUP_CMD = re.compile(
    r"\b(pip install|poetry|conda|npm install|yarn|pnpm|docker(?:-compose)?|"
    r"uvicorn|gunicorn|flask run|python -m|make)\b",
    re.IGNORECASE,
)

_MAX_FEATURES = 12
_MAX_SETUP = 8
# A claim needs at least this many content tokens to be groundable (avoids
# retrieving on a single vague word).
_MIN_TERMS = 2


@dataclass
class ExtractedClaim:
    text: str
    claim_type: ClaimType
    terms: list[str] = field(default_factory=list)


def _clean(text: str) -> str:
    # Drop inline code backticks and markdown links, collapse whitespace.
    text = re.sub(r"`([^`]*)`", r"\1", text)
    text = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", text)
    return " ".join(text.split())


def _dedup_terms(text: str) -> list[str]:
    seen: dict[str, None] = {}
    for tok in tokenize(text):
        seen.setdefault(tok, None)
    return list(seen)


def extract_feature_claims(readme_text: str) -> list[ExtractedClaim]:
    """Bullet points and capability sentences -> groundable feature claims."""
    claims: list[ExtractedClaim] = []
    seen: set[str] = set()
    in_fence = False

    for raw in readme_text.splitlines():
        if _FENCE.match(raw):
            in_fence = not in_fence
            continue
        if in_fence or _HEADING.match(raw):
            continue

        candidate: str | None = None
        m = _BULLET.match(raw)
        if m:
            candidate = _clean(m.group(1))
        elif _FEATURE_VERB.search(raw):
            candidate = _clean(raw)

        if not candidate:
            continue
        key = candidate.lower()
        if key in seen or len(candidate) < 4:
            continue
        terms = _dedup_terms(candidate)
        if len(terms) < _MIN_TERMS:
            continue
        seen.add(key)
        claims.append(ExtractedClaim(candidate, ClaimType.FEATURE, terms))
        if len(claims) >= _MAX_FEATURES:
            break
    return claims


def extract_setup_claims(readme_text: str) -> list[ExtractedClaim]:
    """Setup/run commands from fenced blocks or inline -> groundable setup claims."""
    claims: list[ExtractedClaim] = []
    seen: set[str] = set()
    for raw in readme_text.splitlines():
        if not _SETUP_CMD.search(raw):
            continue
        cmd = _clean(raw.lstrip("$ ").strip("`").strip())
        key = cmd.lower()
        if not cmd or key in seen:
            continue
        seen.add(key)
        claims.append(ExtractedClaim(cmd, ClaimType.SETUP_ENV, _dedup_terms(cmd)))
        if len(claims) >= _MAX_SETUP:
            break
    return claims


def extract_claims(readme_text: str) -> list[ExtractedClaim]:
    """All groundable (non-tech) claims: features first, then setup."""
    if not readme_text.strip():
        return []
    return extract_feature_claims(readme_text) + extract_setup_claims(readme_text)
