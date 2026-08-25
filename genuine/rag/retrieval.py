"""A pure-Python TF-IDF retriever over code chunks.

No numpy, no embeddings, no network — the corpus is one repo's significant
files, so classic sparse TF-IDF cosine is both sufficient and fully auditable
(you can hand-check any score). Tokenization is identifier-aware: an identifier
contributes both its whole lowercased form *and* its camelCase/snake_case parts,
so the query ``fastapi`` matches ``from fastapi import FastAPI`` and ``export
csv`` matches ``def export_csv``.
"""

from __future__ import annotations

import math
import re
from collections import Counter
from dataclasses import dataclass

from .chunking import CodeChunk

# Identifiers, numbers, and dotted words. We then sub-split identifiers.
_WORD_RE = re.compile(r"[A-Za-z][A-Za-z0-9_]*|\d+")
# camelCase / PascalCase / ACRONYMFollowed splitter.
_CAMEL_RE = re.compile(r"[A-Z]+(?=[A-Z][a-z])|[A-Z]?[a-z]+|[A-Z]+|\d+")

# Tiny stoplist — the ultra-common English/code glue that would otherwise
# dominate short README-claim queries. IDF handles the rest.
_STOP = frozenset(
    {
        "the", "a", "an", "and", "or", "of", "to", "in", "for", "on", "with",
        "is", "are", "be", "this", "that", "it", "as", "by", "from", "at",
        "our", "your", "you", "we", "using", "use", "uses", "used", "via",
        "self", "def", "class", "return", "import", "if", "else", "true", "false",
    }
)


def _subtokens(word: str) -> list[str]:
    out = [word.lower()]
    parts = _CAMEL_RE.findall(word)
    if len(parts) > 1:
        out.extend(p.lower() for p in parts)
    return out


def tokenize(text: str) -> list[str]:
    """Text/code -> retrieval tokens (identifier-aware, stopword-filtered)."""
    tokens: list[str] = []
    for word in _WORD_RE.findall(text):
        for tok in _subtokens(word):
            if len(tok) >= 2 and tok not in _STOP:
                tokens.append(tok)
    return tokens


@dataclass
class RetrievedChunk:
    chunk: CodeChunk
    score: float

    @property
    def citation(self) -> str:
        return self.chunk.citation


class Retriever:
    """Build once over a chunk list, then :meth:`query` repeatedly."""

    def __init__(self, chunks: list[CodeChunk]) -> None:
        self.chunks = chunks
        self._tf: list[Counter] = [Counter(tokenize(c.text)) for c in chunks]
        n = len(chunks)

        df: Counter = Counter()
        for tf in self._tf:
            df.update(tf.keys())
        # Smoothed idf, always >= 1 so a term never zeroes out its own weight.
        self._idf: dict[str, float] = {
            term: math.log((n + 1) / (freq + 1)) + 1.0 for term, freq in df.items()
        }
        self._default_idf = math.log((n + 1) / 1) + 1.0 if n else 1.0

        self._norms: list[float] = []
        for tf in self._tf:
            sq = sum((cnt * self._idf.get(term, self._default_idf)) ** 2 for term, cnt in tf.items())
            self._norms.append(math.sqrt(sq))

    def query(self, text: str, k: int = 5) -> list[RetrievedChunk]:
        """Top-``k`` chunks by cosine similarity to ``text`` (score > 0 only)."""
        q_tf = Counter(tokenize(text))
        if not q_tf or not self.chunks:
            return []
        q_weights = {term: cnt * self._idf.get(term, self._default_idf) for term, cnt in q_tf.items()}
        q_norm = math.sqrt(sum(w * w for w in q_weights.values()))
        if q_norm == 0:
            return []

        scored: list[RetrievedChunk] = []
        for chunk, tf, norm in zip(self.chunks, self._tf, self._norms):
            if norm == 0:
                continue
            dot = sum(
                w * tf.get(term, 0) * self._idf.get(term, self._default_idf)
                for term, w in q_weights.items()
            )
            if dot <= 0:
                continue
            scored.append(RetrievedChunk(chunk, round(dot / (norm * q_norm), 4)))

        # Deterministic: score desc, then citation asc to break ties stably.
        scored.sort(key=lambda r: (-r.score, r.chunk.citation))
        return scored[:k]
