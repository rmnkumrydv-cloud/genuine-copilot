"""README-consistency stub tests (spec §6.5). This deterministic half only
*verifies* tech-stack claims — it never uses an LLM — and is deliberately
conservative: it flags a contradiction only when the ecosystem is clearly
present but the named dependency is absent.
"""

from __future__ import annotations

from genuine.models import EvidenceType, FileRecord, VerificationStatus
from genuine.signals.readme_consistency import analyze_readme


def _py(path: str, loc: int = 1) -> FileRecord:
    return FileRecord(path=path, language="python", loc=loc, significance_rank=1)


def test_verified_claim_scores_zero():
    files = [_py("app.py", 3)]
    texts = {"app.py": "import flask\n\napp = flask.Flask(__name__)\n"}
    res = analyze_readme("# Project\nBuilt with Flask.", files, texts)
    assert res.score == 0.0
    assert any(c.verification_status == VerificationStatus.VERIFIED for c in res.claims)
    assert res.evidence == []


def test_contradiction_detected_in_python_repo():
    files = [_py("main.py", 2)]
    texts = {"main.py": "import os\nprint('hi')\n"}
    res = analyze_readme("Built with Flask and Django.", files, texts)
    # Both named, neither present, clearly a Python repo -> both contradicted.
    assert res.score == 1.0
    assert {e.type for e in res.evidence} == {EvidenceType.README_CONTRADICTION}
    assert len(res.evidence) == 2


def test_verified_via_manifest_not_import():
    files = [_py("main.py", 1), FileRecord(path="requirements.txt", language="text", loc=1, significance_rank=99)]
    texts = {"main.py": "print('hi')\n", "requirements.txt": "streamlit==1.30\n"}
    res = analyze_readme("A Streamlit dashboard.", files, texts)
    assert res.score == 0.0
    assert any(c.verification_status == VerificationStatus.VERIFIED for c in res.claims)


def test_ambiguous_claim_stays_unverified():
    """React named but no Node ecosystem present -> UNVERIFIED, no false positive."""
    files = [_py("main.py", 1)]
    texts = {"main.py": "print('hi')\n"}
    res = analyze_readme("Uses React on the frontend.", files, texts)
    assert res.score == 0.0
    assert res.claims and all(
        c.verification_status == VerificationStatus.UNVERIFIED for c in res.claims
    )


def test_empty_readme_scores_zero():
    assert analyze_readme("   ", [_py("main.py")], {"main.py": "x = 1\n"}).score == 0.0
