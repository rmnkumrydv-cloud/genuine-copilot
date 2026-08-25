"""Gate-5 LLM explainer — fully offline tests.

No network: a real Groq call is either faked via an injected ``FakeChat`` or
monkeypatched at :meth:`GroqChat.complete`. An autouse guard turns any
*un-mocked* live call into an immediate failure, so these tests can never hit
the API even though the repo's ``.env`` has a real key.

Covers: JSON parsing → AIOpinion + probes, graceful degradation (no key / API
returns nothing / non-JSON), the malformed-probe filter, the structural input
boundary (no raw-source parameter), and the neuro-symbolic invariant — turning
the explainer on never changes the verdict or composite score.
"""

from __future__ import annotations

import inspect
import json

import pytest

from genuine.llm import explain, is_available, review
from genuine.llm.client import GroqChat
from genuine.llm.explainer import LLMReview, _context
from genuine.models import (
    EvidenceItem,
    EvidenceType,
    ScoreResult,
    SubScore,
    Verdict,
)
from genuine.pipeline import analyze


# --------------------------------------------------------------------------- #
# Test doubles / helpers                                                       #
# --------------------------------------------------------------------------- #
class FakeChat:
    """Drop-in for GroqChat: records calls, returns a canned response."""

    def __init__(self, response, available: bool = True):
        self._response = response
        self._available = available
        self.calls: list[tuple] = []

    @property
    def available(self) -> bool:
        return self._available

    def complete(self, system, user, *, temperature=0.3, max_tokens=900, json_mode=False):
        self.calls.append((system, user, {"json_mode": json_mode, "temperature": temperature}))
        if not self._available:  # mirror the real wrapper's guard
            return None
        return self._response


def _score(verdict: Verdict = Verdict.FLAGGED, with_evidence: bool = True) -> ScoreResult:
    evidence = []
    if with_evidence:
        evidence = [
            EvidenceItem(
                id="e1",
                type=EvidenceType.CLONE_MATCH,
                feeds=SubScore.CLONE_SIMILARITY,
                summary="3 file(s) closely match alice/inventory (logic 0.95)",
                confidence=0.9,
            )
        ]
    return ScoreResult(
        clone_similarity_score=0.9,
        composite_score=0.45,
        coverage_ratio=0.8,
        commit_count=5,
        verdict=verdict,
        evidence=evidence,
    )


@pytest.fixture(autouse=True)
def _no_live_groq(monkeypatch):
    """Any GroqChat.complete not explicitly overridden by a test is a hard fail."""

    def _boom(self, *a, **k):
        raise AssertionError("a live Groq call was attempted in a test")

    monkeypatch.setattr(GroqChat, "complete", _boom)


# --------------------------------------------------------------------------- #
# Parsing / happy path                                                         #
# --------------------------------------------------------------------------- #
def test_review_builds_opinion_and_probes():
    payload = {
        "explanation": "The code closely matches an older repo; verify authorship.",
        "interview_questions": [
            {"question": "Walk me through your diff algorithm.", "targets": "clone_similarity"},
            {"question": "Why this data structure?", "targets": "general"},
        ],
    }
    fake = FakeChat(json.dumps(payload))
    result = review(_score(), repo_name="bob/thing", chat=fake)

    assert result.available
    assert result.ai_opinion is not None
    assert result.ai_opinion.summary.startswith("The code closely matches")
    assert result.ai_opinion.label == "advisory_only"  # hardcoded, cannot read as a verdict
    assert result.ai_opinion.source == "ScoreResult + retrieved evidence chunks"
    assert result.ai_opinion.review_id.startswith("rev_")
    assert [p.question for p in result.interview_probes] == [
        "Walk me through your diff algorithm.",
        "Why this data structure?",
    ]
    assert result.interview_probes[0].targets_evidence_id == "clone_similarity"

    # The model was given the verdict + evidence summary and asked for JSON.
    _system, user_prompt, kwargs = fake.calls[0]
    assert "flagged" in user_prompt
    assert "3 file(s) closely match alice/inventory" in user_prompt
    assert kwargs["json_mode"] is True


def test_explain_returns_just_the_opinion():
    fake = FakeChat(json.dumps({"explanation": "Looks fine.", "interview_questions": []}))
    opinion = explain(_score(Verdict.CLEAN), chat=fake)
    assert opinion is not None and opinion.summary == "Looks fine."


def test_review_id_is_deterministic():
    s = _score()
    a = review(s, repo_name="x/y", chat=FakeChat(json.dumps({"explanation": "e"})))
    b = review(s, repo_name="x/y", chat=FakeChat(json.dumps({"explanation": "e"})))
    assert a.ai_opinion.review_id == b.ai_opinion.review_id


# --------------------------------------------------------------------------- #
# Graceful degradation                                                         #
# --------------------------------------------------------------------------- #
def test_review_empty_when_no_key():
    result = review(_score(), chat=FakeChat("unused", available=False))
    assert result.ai_opinion is None
    assert result.interview_probes == []
    assert not result.available


def test_review_empty_when_api_returns_nothing():
    # available, but the call failed (wrapper collapses errors to None)
    result = review(_score(), chat=FakeChat(None, available=True))
    assert result.ai_opinion is None and result.interview_probes == []


def test_review_uses_plain_text_when_not_json():
    result = review(_score(), chat=FakeChat("plain prose, not json"))
    assert result.ai_opinion is not None
    assert result.ai_opinion.summary == "plain prose, not json"
    assert result.interview_probes == []


def test_parse_probes_skips_malformed_items():
    raw = json.dumps(
        {
            "explanation": "ok",
            "interview_questions": [
                {"question": "keep me", "targets": "t"},
                {"targets": "no question field"},  # dropped
                "a bare string",  # dropped
                {"question": "   "},  # blank -> dropped
                {"question": "no targets"},  # kept, defaults to 'general'
            ],
        }
    )
    result = review(_score(), chat=FakeChat(raw))
    assert [p.question for p in result.interview_probes] == ["keep me", "no targets"]
    assert result.interview_probes[1].targets_evidence_id == "general"


def test_context_handles_no_evidence():
    text = _context(_score(Verdict.INSUFFICIENT_SIGNAL, with_evidence=False), "solo/repo")
    assert "no deterministic signal fired" in text
    assert "insufficient_signal" in text


def test_is_available_reflects_the_chat():
    assert is_available(FakeChat("x", available=True)) is True
    assert is_available(FakeChat("x", available=False)) is False


# --------------------------------------------------------------------------- #
# Structural input boundary (prompt-injection closure)                         #
# --------------------------------------------------------------------------- #
def test_input_boundary_has_no_raw_source_parameter():
    """The explainer can only be handed a ScoreResult + repo name — never source,
    README, files, or the full analysis. This is what closes prompt injection."""
    forbidden = {
        "source", "sources", "texts", "code", "readme", "readme_text",
        "files", "raw", "analysis",
    }
    for fn in (review, explain, _context):
        params = set(inspect.signature(fn).parameters)
        assert not (params & forbidden), f"{fn.__name__} exposes a raw-content param"

    assert set(inspect.signature(review).parameters) <= {"score", "repo_name", "chat"}
    assert set(inspect.signature(explain).parameters) <= {"score", "repo_name", "chat"}


# --------------------------------------------------------------------------- #
# Neuro-symbolic invariant, end to end through the pipeline                    #
# --------------------------------------------------------------------------- #
_FIXED_JSON = json.dumps(
    {
        "explanation": "Advisory prose about the verdict.",
        "interview_questions": [{"question": "Explain module a.py.", "targets": "general"}],
    }
)


def test_explanation_never_changes_the_verdict(make_git_repo, tmp_db, cache_root, monkeypatch):
    repo = make_git_repo(
        "explain",
        [{"message": "init", "files": {"a.py": "def f():\n    return 1\n"},
          "date": "2024-01-01 10:00:00 +0000"}],
    )
    # register_in_registry=False on BOTH runs: otherwise the first run would
    # register this repo and the second would match its own fingerprint, moving
    # the composite and defeating the comparison.
    off = analyze(str(repo), db_path=tmp_db, cache_root=cache_root,
                  register_in_registry=False, explain=False)

    monkeypatch.setattr(GroqChat, "complete", lambda self, s, u, **k: _FIXED_JSON)
    on = analyze(str(repo), db_path=tmp_db, cache_root=cache_root,
                 register_in_registry=False, explain=True)

    # The deterministic result is byte-for-byte identical with the LLM on vs off.
    assert off.score.verdict == on.score.verdict
    assert off.score.composite_score == on.score.composite_score
    assert off.score.sub_scores() == on.score.sub_scores()

    # ...and off produced no advisory content, on did.
    assert off.ai_opinion is None and off.interview_probes == []
    assert on.ai_opinion is not None
    assert on.ai_opinion.label == "advisory_only"
    assert on.ai_opinion.summary == "Advisory prose about the verdict."
    assert [p.question for p in on.interview_probes] == ["Explain module a.py."]

    payload = on.to_payload()
    assert payload["ai_opinion"]["label"] == "advisory_only"
    assert payload["interview_probes"][0]["question"] == "Explain module a.py."


def test_pipeline_falls_back_when_llm_unavailable(make_git_repo, tmp_db, cache_root, monkeypatch):
    """explain=True but the call yields nothing -> deterministic report stands,
    payload carries a null ai_opinion (stable schema)."""
    monkeypatch.setattr(GroqChat, "complete", lambda self, s, u, **k: None)
    repo = make_git_repo(
        "fallback",
        [{"message": "init", "files": {"a.py": "def f():\n    return 2\n"},
          "date": "2024-01-01 10:00:00 +0000"}],
    )
    result = analyze(str(repo), db_path=tmp_db, cache_root=cache_root,
                     register_in_registry=False, explain=True)
    assert result.ai_opinion is None
    assert result.interview_probes == []
    assert result.report_text  # the template report is still there
    assert result.to_payload()["ai_opinion"] is None
