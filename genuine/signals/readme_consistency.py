"""README consistency — deterministic Gate-2 stub (spec §6.5).

The full version (Gate 4) uses an LLM to *extract* claims and RAG to locate the
candidate code region; verification stays deterministic. This stub implements
only the verification half for **tech-stack** claims, with no AI: it checks
whether a technology named in the README is actually present in imports/manifests.

Deliberately conservative — a claim is only ``contradicted`` when the relevant
ecosystem is present but the specific dependency is absent (README says "built
with Flask", it's clearly a Python repo, yet nothing imports flask). Anything
ambiguous stays ``unverified`` and contributes nothing to the score, so the stub
does not manufacture false positives in the demo.
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
    "react": ("node", {"react"}),
    "vue": ("node", {"vue"}),
    "angular": ("node", {"@angular", "angular"}),
    "express": ("node", {"express"}),
    "next.js": ("node", {"next"}),
    "nextjs": ("node", {"next"}),
    "svelte": ("node", {"svelte"}),
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


@dataclass
class ReadmeResult:
    score: float  # readme_consistency suspicion in [0, 1]
    claims: list[ReadmeClaim] = field(default_factory=list)
    evidence: list[EvidenceItem] = field(default_factory=list)


def _python_import_roots(texts: dict[str, str]) -> set[str]:
    roots: set[str] = set()
    for path, src in texts.items():
        if not path.endswith(".py"):
            continue
        try:
            tree = ast.parse(src)
        except (SyntaxError, ValueError):
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                roots.update(a.name.split(".")[0].lower() for a in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                roots.add(node.module.split(".")[0].lower())
    return roots


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
    import_roots = _python_import_roots(texts)
    haystack = manifest_blob + " " + " ".join(import_roots)

    python_present = any(p.endswith(".py") for p in paths) or "requirements.txt" in " ".join(paths) or any(
        p.endswith("pyproject.toml") for p in paths
    )
    node_present = any(p.endswith("package.json") for p in paths)
    ecosystem_present = {"python": python_present, "node": node_present}

    readme_lc = readme_text.lower()
    claims: list[ReadmeClaim] = []
    evidence: list[EvidenceItem] = []
    verifiable = 0
    contradicted = 0

    for tech, (ecosystem, tokens) in _TECH_CHECKS.items():
        if not re.search(rf"\b{re.escape(tech)}\b", readme_lc):
            continue
        found = any(tok in haystack for tok in tokens)
        if found:
            status = VerificationStatus.VERIFIED
            verifiable += 1
        elif ecosystem_present.get(ecosystem):
            status = VerificationStatus.CONTRADICTED
            verifiable += 1
            contradicted += 1
            evidence.append(
                EvidenceItem(
                    id=f"readme_{tech.replace('.', '')}",
                    type=EvidenceType.README_CONTRADICTION,
                    feeds=SubScore.README_CONSISTENCY,
                    summary=f'README claims "{tech}" but it is not imported or '
                    f"declared anywhere in this {ecosystem} project",
                    detail={"tech": tech, "ecosystem": ecosystem, "expected_tokens": sorted(tokens)},
                    confidence=0.7,
                )
            )
        else:
            status = VerificationStatus.UNVERIFIED
        claims.append(
            ReadmeClaim(claim_text=f"Uses {tech}", claim_type=ClaimType.TECH_STACK, verification_status=status)
        )

    score = round(contradicted / verifiable, 4) if verifiable else 0.0
    return ReadmeResult(score=score, claims=claims, evidence=evidence)
