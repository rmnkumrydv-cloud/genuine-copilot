"""Gate 4 — retrieval-augmented grounding (spec §6.5, RAG half).

Deterministic, offline, no ML wheels. Three pieces:

* :mod:`genuine.rag.chunking` — split source into retrievable regions
  (AST-aware for Python: one chunk per top-level def/class; line windows
  otherwise), each carrying a ``path:start-end`` citation.
* :mod:`genuine.rag.retrieval` — a pure-Python TF-IDF retriever over those
  chunks, with identifier-aware tokenization (``from fastapi import`` is
  findable by the query ``fastapi``).
* :mod:`genuine.rag.claims` — richer deterministic README claim extraction
  (feature + setup claims), each with the query terms used to ground it.

**Why this respects the neuro-symbolic boundary:** retrieval feeds the
*deterministic* verifier (``genuine.signals.readme_consistency``), producing
evidence with concrete ``file:line`` citations. The LLM explainer (Gate 5)
still sees only symbolic outputs — never the retrieved source — so the
prompt-injection closure is intact.
"""

from __future__ import annotations

from .chunking import CodeChunk, chunk_file, chunk_repo
from .claims import ExtractedClaim, extract_claims
from .retrieval import RetrievedChunk, Retriever

__all__ = [
    "CodeChunk",
    "chunk_file",
    "chunk_repo",
    "ExtractedClaim",
    "extract_claims",
    "RetrievedChunk",
    "Retriever",
]
