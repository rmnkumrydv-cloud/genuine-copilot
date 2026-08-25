"""Shared hash registry (spec §6.4, §8.4-7).

Every analyzed repo's MinHash fingerprint is stored. A new submission is checked
against the growing registry to catch near-identical submissions *between
candidates* — a collusion/duplication failure mode that public-web search misses
entirely.

Two integrity rules:

* **Registry isolation** (§8.4-7): the check excludes the target's own slug and
  owner, so a re-analysis of an already-registered repo can't match itself.
* **Check before register**: we compare against existing rows first, then upsert
  — order matters for the same reason.

The check is a linear scan of stored signatures computing estimated Jaccard. For
a large registry, swap in ``datasketch.MinHashLSH`` for sub-linear lookup — same
result, the scan is just the simple, auditable version.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field

from ..ingestion.fingerprint import estimated_jaccard
from ..models import EvidenceItem, EvidenceType, RepoAnalysis, SubScore
from ..store import connect

# Estimated-Jaccard at/above which we treat two submissions as near-duplicates.
DUPLICATE_THRESHOLD = 0.5


@dataclass
class RegistryResult:
    score: float  # registry_match suspicion in [0, 1]
    evidence: list[EvidenceItem] = field(default_factory=list)
    nearest: list[tuple[str, float]] = field(default_factory=list)  # (slug, jaccard)


def _slug(target: RepoAnalysis) -> str:
    return f"{target.owner}/{target.repo_name}" if target.owner else target.repo_name


def check(db_path, target: RepoAnalysis) -> RegistryResult:
    """Compare the target's fingerprint against all *other* stored submissions."""
    target_slug = _slug(target)
    rows = []
    with connect(db_path) as conn:
        for row in conn.execute(
            "SELECT slug, owner, fingerprint FROM submissions"
        ).fetchall():
            # Registry isolation: never match against self or same owner.
            if row["slug"] == target_slug or (target.owner and row["owner"] == target.owner):
                continue
            rows.append((row["slug"], json.loads(row["fingerprint"])))

    scored = [
        (slug, estimated_jaccard(target.fingerprint, sig)) for slug, sig in rows
    ]
    scored.sort(key=lambda x: -x[1])
    best = scored[0][1] if scored else 0.0

    evidence: list[EvidenceItem] = []
    for slug, jac in scored:
        if jac >= DUPLICATE_THRESHOLD:
            evidence.append(
                EvidenceItem(
                    id=f"registry_{slug.replace('/', '_')}",
                    type=EvidenceType.REGISTRY_MATCH,
                    feeds=SubScore.REGISTRY_MATCH,
                    summary=f"Near-duplicate of previously submitted repo {slug} "
                    f"(fingerprint overlap {jac:.2f})",
                    detail={"candidate_slug": slug, "estimated_jaccard": round(jac, 4)},
                    confidence=round(jac, 4),
                )
            )
    return RegistryResult(score=round(best, 4), evidence=evidence, nearest=scored[:5])


def register(db_path, target: RepoAnalysis) -> None:
    """Upsert the target's fingerprint into the registry (idempotent by slug)."""
    with connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO submissions (slug, repo_url, owner, repo_name, fingerprint,
                                     repo_created_at, ingested_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(slug) DO UPDATE SET
                fingerprint=excluded.fingerprint,
                repo_url=excluded.repo_url,
                ingested_at=excluded.ingested_at
            """,
            (
                _slug(target),
                target.repo_url,
                target.owner,
                target.repo_name,
                json.dumps(target.fingerprint),
                target.repo_created_at.isoformat() if target.repo_created_at else None,
                target.ingested_at.isoformat(),
            ),
        )
