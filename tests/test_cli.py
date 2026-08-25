"""CLI smoke tests — the ``genuine analyze`` console entry point (a Gate-1
deliverable). Env vars point the registry at a temp DB so the CLI never writes
to the real one.
"""

from __future__ import annotations

import json

import pytest

from genuine.cli import main
from conftest import FIXTURES


@pytest.fixture(autouse=True)
def _temp_settings(tmp_path, monkeypatch):
    monkeypatch.setenv("GENUINE_DB_PATH", str(tmp_path / "cli.sqlite"))
    monkeypatch.setenv("GENUINE_CLONE_CACHE", str(tmp_path / "clones"))
    from genuine.config import get_settings

    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def test_cli_text_report(capsys):
    code = main(["analyze", str(FIXTURES / "original")])
    assert code == 0
    out = capsys.readouterr().out
    # A plain directory has no git history -> insufficient signal, never accused.
    assert "INSUFFICIENT SIGNAL" in out
    assert "no LLM" in out  # the neuro-symbolic promise is printed


def test_cli_json_payload(capsys):
    code = main(["analyze", str(FIXTURES / "original"), "--json"])
    assert code == 0
    payload = json.loads(capsys.readouterr().out)
    assert set(payload["sub_scores"]) == {
        "clone_similarity", "readme_consistency", "commit_forensics", "registry_match"
    }
    assert payload["verdict"] == "insufficient_signal"


def test_cli_with_candidate_flags_copy(capsys):
    """`--candidate` pointing at the original flags a renamed copy of it."""
    code = main([
        "analyze", str(FIXTURES / "renamed"),
        "--candidate", str(FIXTURES / "original"),
        "--no-register", "--json",
    ])
    assert code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["sub_scores"]["clone_similarity"] > 0.8
