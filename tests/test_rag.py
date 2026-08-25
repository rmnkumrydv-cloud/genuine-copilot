"""Gate 4 — RAG chunking, retrieval, claim extraction, and grounding.

All deterministic and offline. The integration tests double as regression guards
proving the RAG layer is *additive*: it enriches claims/evidence with citations
but never moves the deterministic README-consistency score.
"""

from __future__ import annotations

from genuine.models import ClaimType, FileRecord, VerificationStatus
from genuine.rag import Retriever, chunk_file, chunk_repo, extract_claims
from genuine.rag.claims import extract_feature_claims, extract_setup_claims
from genuine.rag.retrieval import tokenize
from genuine.signals.readme_consistency import analyze_readme

VERIFIED = VerificationStatus.VERIFIED
UNVERIFIED = VerificationStatus.UNVERIFIED
CONTRADICTED = VerificationStatus.CONTRADICTED


def _py(path: str, loc: int = 3) -> FileRecord:
    return FileRecord(path=path, language="python", loc=loc, significance_rank=1)


# --------------------------------------------------------------------------- #
# Chunking                                                                     #
# --------------------------------------------------------------------------- #
_SAMPLE = """import os
from math import sqrt

X = 1

def foo(a):
    return a + 1

@decorator
def bar():
    return 2

class Baz:
    def method(self):
        return 3
"""


def test_python_chunks_split_by_top_level_symbol():
    chunks = chunk_file("m.py", _SAMPLE)
    symbols = {c.symbol for c in chunks}
    assert {"<module>", "foo", "bar", "Baz"} <= symbols

    bar = next(c for c in chunks if c.symbol == "bar")
    assert "@decorator" in bar.text  # decorator line folded into the chunk
    header = next(c for c in chunks if c.symbol == "<module>")
    assert "import os" in header.text
    # Citations are locations, not content.
    assert all(c.citation == f"{c.path}:{c.start_line}-{c.end_line}" for c in chunks)


def test_non_python_uses_line_windows():
    src = "\n".join(f"line {i}" for i in range(1, 121))
    chunks = chunk_file("app.js", src)
    assert len(chunks) >= 2
    assert chunks[0].start_line == 1
    assert chunks[0].symbol == ""  # windows have no symbol


def test_unparseable_python_falls_back_to_windows():
    chunks = chunk_file("broken.py", "def (:\n    this is not python\n")
    assert chunks and all(c.symbol == "" for c in chunks)


# --------------------------------------------------------------------------- #
# Tokenization + retrieval                                                     #
# --------------------------------------------------------------------------- #
def test_tokenize_splits_camel_and_snake_case():
    toks = set(tokenize("export_csv FastAPI"))
    assert {"export", "csv", "fastapi", "fast", "api"} <= toks
    assert "the" not in tokenize("the fast api")  # stopword filtered


def test_retriever_ranks_relevant_chunk_first():
    texts = {
        "auth.py": "def login(user, password):\n    return verify(password)\n",
        "mathy.py": "def add(a, b):\n    return a + b\n",
    }
    hits = Retriever(chunk_repo(texts)).query("password login", k=2)
    assert hits and hits[0].chunk.path == "auth.py"


def test_retriever_finds_import_by_identifier():
    texts = {"app.py": "from fastapi import FastAPI\n\napp = FastAPI()\n"}
    hits = Retriever(chunk_repo(texts)).query("fastapi", k=1)
    assert hits and hits[0].chunk.path == "app.py"


def test_retriever_empty_query_returns_nothing():
    r = Retriever(chunk_repo({"a.py": "def f():\n    return 1\n"}))
    assert r.query("the and of") == []  # all stopwords


# --------------------------------------------------------------------------- #
# Claim extraction                                                             #
# --------------------------------------------------------------------------- #
def test_feature_extraction_from_bullets_and_verbs():
    readme = (
        "# Features\n\n"
        "- CSV export of monthly reports\n"
        "- Interactive dashboard\n\n"
        "It also supports PDF generation.\n"
    )
    texts = [c.text for c in extract_feature_claims(readme)]
    assert "CSV export of monthly reports" in texts
    assert any("PDF generation" in t for t in texts)


def test_feature_extraction_ignores_headings_and_fences():
    readme = "## Setup\n```\n- not a real feature bullet\npip install x\n```\n"
    assert extract_feature_claims(readme) == []


def test_setup_extraction_picks_up_commands():
    readme = "## Install\n```\npip install -r requirements.txt\nuvicorn genuine.api:app --reload\n```\n"
    setups = extract_setup_claims(readme)
    assert len(setups) == 2
    assert any("pip install" in c.text for c in setups)
    assert all(c.claim_type == ClaimType.SETUP_ENV for c in setups)


def test_extract_claims_empty_readme():
    assert extract_claims("   ") == []


# --------------------------------------------------------------------------- #
# Integration: grounding is additive, never changes the score                 #
# --------------------------------------------------------------------------- #
def test_verified_tech_gets_a_citation():
    res = analyze_readme(
        "Built with Flask.",
        [_py("app.py")],
        {"app.py": "import flask\n\napp = flask.Flask(__name__)\n"},
    )
    tech = [c for c in res.claims if c.claim_type == ClaimType.TECH_STACK]
    assert tech and tech[0].verification_status == VERIFIED
    assert tech[0].evidence_ref == "app.py"  # RAG located where it lives
    assert res.score == 0.0


def test_feature_claim_grounded_to_code_is_verified():
    readme = "## Features\n\n- CSV export of reports\n"
    texts = {
        "reports.py": (
            "import csv\n\n"
            "def export_csv(rows):\n"
            "    writer = csv.writer(open('out.csv', 'w'))\n"
            "    writer.writerows(rows)\n"
        )
    }
    res = analyze_readme(readme, [_py("reports.py", loc=5)], texts)
    feat = [c for c in res.claims if c.claim_type == ClaimType.FEATURE]
    assert feat and feat[0].verification_status == VERIFIED
    assert feat[0].evidence_ref and feat[0].evidence_ref.startswith("reports.py:")
    assert res.score == 0.0  # feature grounding never touches the score


def test_ungrounded_feature_is_unverified_not_contradicted():
    """A feature not found in code is UNVERIFIED — never a false-positive flag."""
    res = analyze_readme(
        "## Features\n\n- Blockchain consensus engine\n",
        [_py("app.py")],
        {"app.py": "def add(a, b):\n    return a + b\n"},
    )
    feat = [c for c in res.claims if c.claim_type == ClaimType.FEATURE]
    assert feat and feat[0].verification_status == UNVERIFIED
    assert all(c.verification_status != CONTRADICTED for c in res.claims)
    assert res.score == 0.0


def test_contradiction_score_unchanged_and_cites_regions_checked():
    """Regression: the deterministic contradiction path is byte-identical, plus
    the evidence now records which regions RAG searched."""
    res = analyze_readme(
        "Built with Flask and Django.",
        [_py("main.py")],
        {"main.py": "import os\nprint('hi')\n"},
    )
    assert res.score == 1.0
    assert len(res.evidence) == 2
    assert all("regions_checked" in e.detail for e in res.evidence)
