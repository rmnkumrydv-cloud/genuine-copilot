"""LLM layer (Gate 5) — advisory explanation + interview prep over the FINAL,
deterministic verdict.

Hard boundary (this is the whole point of the neuro-symbolic design):

* **Input** is a finished :class:`~genuine.models.ScoreResult` plus its
  human-safe evidence *summaries* — never raw repo source or README text. A
  malicious repo therefore has no channel to inject instructions into the model
  (prompt-injection closure), and the model literally cannot see the code it is
  describing.
* **Output** is prose and interview questions. It never re-enters scoring — the
  aggregator has no parameter for it (see
  ``tests/test_scoring.py::test_aggregate_signature_has_no_ai_opinion_param``).

If no ``GROQ_API_KEY`` is set (or the SDK/API is unavailable), every entry point
degrades to ``None`` / ``[]`` and the deterministic template report stands alone.
"""

from __future__ import annotations

from .client import GroqChat
from .explainer import LLMReview, explain, is_available, review

__all__ = ["GroqChat", "LLMReview", "explain", "is_available", "review"]
