"""README consistency (spec §6.5) — deterministic verification, RAG grounding.

Two layers, and the split is the whole point of the neuro-symbolic design:

* **Scoring (deterministic, auditable):** tech-stack claims only. A claim is
  ``contradicted`` — the only thing that raises suspicion — solely when the
  relevant ecosystem is clearly present but the named dependency is absent
  (README says "built with Flask", it's plainly a Python repo, yet nothing
  imports flask). Everything ambiguous stays ``unverified`` and scores nothing.
  The score is ``contradicted / verifiable`` and depends on *nothing* from the
  RAG layer below.

* **Grounding (RAG, advisory):** retrieval (``genuine.rag``) locates the code
  region behind a claim, so verified tech carries a ``file:line`` citation and
  softer *feature/setup* claims get grounded to code. These enrich the evidence
  a human reads; they never feed the suspicion score.
"""

from __future__ import annotations

import ast
import re
from dataclasses import dataclass, field

from ..models import (
    ClaimType,
    EvidenceItem,
    EvidenceType,
    FileRecord,
    ReadmeClaim,
    SubScore,
    VerificationStatus,
)
from ..rag import Retriever, chunk_repo, extract_claims

# tech label -> (ecosystem, evidence tokens to look for in imports/manifests)
_TECH_CHECKS: dict[str, tuple[str, set[str]]] = {
    "flask": ("python", {"flask"}),
    "django": ("python", {"django"}),
    "fastapi": ("python", {"fastapi"}),
    "pytorch": ("python", {"torch"}),
    "tensorflow": ("python", {"tensorflow"}),
    "streamlit": ("python", {"streamlit"}),
    "pandas": ("python", {"pandas"}),
    "sqlalchemy": ("python", {"sqlalchemy"}),
    # data stores / infra (python drivers)
    "redis": ("python", {"redis"}),
    "celery": ("python", {"celery"}),
    "mongodb": ("python", {"pymongo", "mongoengine", "motor"}),
    "postgresql": ("python", {"psycopg2", "psycopg", "asyncpg"}),
    "postgres": ("python", {"psycopg2", "psycopg", "asyncpg"}),
    # scientific / ML
    "numpy": ("python", {"numpy"}),
    "scipy": ("python", {"scipy"}),
    "scikit-learn": ("python", {"sklearn"}),
    "sklearn": ("python", {"sklearn"}),
    "transformers": ("python", {"transformers"}),
    "langchain": ("python", {"langchain"}),
    "openai": ("python", {"openai"}),
    "groq": ("python", {"groq"}),
    # http clients
    "aiohttp": ("python", {"aiohttp"}),
    "httpx": ("python", {"httpx"}),
    # node / frontend
    "react": ("node", {"react"}),
    "vue": ("node", {"vue"}),
    "angular": ("node", {"@angular", "angular"}),
    "express": ("node", {"express"}),
    "next.js": ("node", {"next"}),
    "nextjs": ("node", {"next"}),
    "svelte": ("node", {"svelte"}),
    "tailwind": ("node", {"tailwindcss"}),
    "tailwindcss": ("node", {"tailwindcss"}),
    "vite": ("node", {"vite"}),
    "typescript": ("node", {"typescript"}),
}

_MANIFESTS = (
    "requirements.txt",
    "pyproject.toml",
    "setup.py",
    "setup.cfg",
    "pipfile",
    "environment.yml",
    "package.json",
)

# A grounded (feature/setup) claim needs at least this retrieval cosine to count
# as located in the code. Conservative: below it the claim stays UNVERIFIED —
# "we couldn't find it", never "it's contradicted".
_GROUND_THRESHOLD = 0.1


@dataclass
class ReadmeResult:
    score: float  # readme_consistency suspicion in [0, 1]
    claims: list[ReadmeClaim] = field(default_factory=list)
    evidence: list[EvidenceItem] = field(default_factory=list)


def _import_roots_by_file(texts: dict[str, str]) -> dict[str, set[str]]:
    """Per-file top-level import roots, so a verified tech can cite where it lives."""
    out: dict[str, set[str]] = {}
    for path, src in texts.items():
        if not path.endswith(".py"):
            continue
        try:
            tree = ast.parse(src)
        except (SyntaxError, ValueError):
            continue
        roots: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                roots.update(a.name.split(".")[0].lower() for a in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                roots.add(node.module.split(".")[0].lower())
        if roots:
            out[path] = roots
    return out


def _cite_tech(tokens: set[str], roots_by_file: dict[str, set[str]], texts: dict[str, str]) -> str | None:
    """First file that imports the tech, else first manifest that declares it."""
    for path in sorted(roots_by_file):
        if roots_by_file[path] & tokens:
            return path
    for path in sorted(texts):
        if any(path.lower().endswith(m) for m in _MANIFESTS) and any(
            tok in texts[path].lower() for tok in tokens
        ):
            return path
    return None


def _ground_claims(retriever: Retriever, readme_text: str) -> list[ReadmeClaim]:
    """Feature/setup claims located in code via retrieval. Advisory, non-scoring:
    a hit -> VERIFIED with a citation; a miss -> UNVERIFIED (never CONTRADICTED)."""
    grounded: list[ReadmeClaim] = []
    for claim in extract_claims(readme_text):
        hits = retriever.query(" ".join(claim.terms), k=1)
        if hits and hits[0].score >= _GROUND_THRESHOLD:
            grounded.append(
                ReadmeClaim(
                    claim_text=claim.text,
                    claim_type=claim.claim_type,
                    verification_status=VerificationStatus.VERIFIED,
                    evidence_ref=hits[0].citation,
                )
            )
        else:
            grounded.append(
                ReadmeClaim(
                    claim_text=claim.text,
                    claim_type=claim.claim_type,
                    verification_status=VerificationStatus.UNVERIFIED,
                )
            )
    return grounded


def analyze_readme(
    readme_text: str, files: list[FileRecord], texts: dict[str, str]
) -> ReadmeResult:
    if not readme_text.strip():
        return ReadmeResult(score=0.0)

    paths = {f.path.lower() for f in files}
    manifest_blob = " ".join(
        src.lower()
        for path, src in texts.items()
        if any(path.lower().endswith(m) for m in _MANIFESTS)
    )
    roots_by_file = _import_roots_by_file(texts)
    import_roots: set[str] = set().union(*roots_by_file.values()) if roots_by_file else set()
    haystack = manifest_blob + " " + " ".join(import_roots)

    python_present = any(p.endswith(".py") for p in paths) or "requirements.txt" in " ".join(paths) or any(
        p.endswith("pyproject.toml") for p in paths
    )
    node_present = any(p.endswith("package.json") for p in paths)
    ecosystem_present = {"python": python_present, "node": node_present}

    # RAG index over the significant-file sources (used only for grounding/citations).
    retriever = Retriever(chunk_repo(texts))

    readme_lc = readme_text.lower()
    claims: list[ReadmeClaim] = []
    evidence: list[EvidenceItem] = []
    verifiable = 0
    contradicted = 0

    for tech, (ecosystem, tokens) in _TECH_CHECKS.items():
        if not re.search(rf"\b{re.escape(tech)}\b", readme_lc):
            continue
        found = any(tok in haystack for tok in tokens)
        citation: str | None = None
        if found:
            status = VerificationStatus.VERIFIED
            verifiable += 1
            citation = _cite_tech(tokens, roots_by_file, texts)
        elif ecosystem_present.get(ecosystem):
            status = VerificationStatus.CONTRADICTED
            verifiable += 1
            contradicted += 1
            # Show the reviewer which regions were searched (and came up empty).
            regions = [rc.citation for rc in retriever.query(tech, k=3)]
            evidence.append(
                EvidenceItem(
                    id=f"readme_{tech.replace('.', '')}",
                    type=EvidenceType.README_CONTRADICTION,
                    feeds=SubScore.README_CONSISTENCY,
                    summary=f'README claims "{tech}" but it is not imported or '
                    f"declared anywhere in this {ecosystem} project",
                    detail={
                        "tech": tech,
                        "ecosystem": ecosystem,
                        "expected_tokens": sorted(tokens),
                        "regions_checked": regions,
                    },
                    confidence=0.7,
                )
            )
        else:
            status = VerificationStatus.UNVERIFIED
        claims.append(
            ReadmeClaim(
                claim_text=f"Uses {tech}",
                claim_type=ClaimType.TECH_STACK,
                verification_status=status,
                evidence_ref=citation,
            )
        )

    # Advisory RAG grounding of feature/setup claims — appended, never scored.
    claims.extend(_ground_claims(retriever, readme_text))

    score = round(contradicted / verifiable, 4) if verifiable else 0.0
    return ReadmeResult(score=score, claims=claims, evidence=evidence)
