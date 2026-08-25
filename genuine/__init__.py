"""Genuine — neuro-symbolic project authenticity & interview-prep copilot.

The package is split along the neuro-symbolic boundary that the whole pitch
rests on:

* ``genuine.ingestion``  — pull a repo into a :class:`~genuine.models.RepoAnalysis`.
* ``genuine.signals``    — DETERMINISTIC signal engines. Every originality
  judgment lives here. No LLM, no ML opinion.
* ``genuine.scoring``    — declarative ``rules.yaml`` aggregator + verdict logic.
* ``genuine.explain``    — (later) RAG + LLM explainer. Reads ScoreResult +
  retrieved evidence only. Never decides a verdict.

If a component would let an LLM decide *what counts as original*, it does not
belong in this package. That rule is the product.
"""

__version__ = "0.1.0"
