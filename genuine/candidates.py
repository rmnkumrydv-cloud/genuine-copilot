"""Build :class:`CandidateRepo` objects for clone comparison.

Candidates can come from three places (spec §13-Q1): the shared registry, a live
GitHub code search (a later enhancement — needs a token + rate limiting), or an
explicit local directory. This module handles the local-directory case, which is
what powers offline demos and the fixture-based tests.
"""

from __future__ import annotations

from datetime import timezone
from pathlib import Path
from typing import Optional

from .ingestion.languages import classify_exclusion
from .signals.clone import CandidateRepo


def _earliest_commit_date(root: Path):
    if not (root / ".git").exists():
        return None
    try:
        from git import Repo

        repo = Repo(str(root))
        commits = list(repo.iter_commits())
        if not commits:
            return None
        ts = commits[-1].committed_datetime  # iter_commits is newest-first
        return ts if ts.tzinfo else ts.replace(tzinfo=timezone.utc)
    except Exception:
        return None


def candidate_from_path(
    path: str | Path,
    slug: Optional[str] = None,
    owner: Optional[str] = None,
    created_at=None,
    max_file_bytes: int = 1_000_000,
) -> CandidateRepo:
    root = Path(path).resolve()
    files: dict[str, str] = {}
    for fp in sorted(root.rglob("*")):
        if not fp.is_file() or ".git" in fp.parts:
            continue
        rel = fp.relative_to(root).as_posix()
        if classify_exclusion(rel):
            continue
        try:
            if fp.stat().st_size > max_file_bytes:
                continue
            files[rel] = fp.read_text(encoding="utf-8", errors="strict")
        except (UnicodeDecodeError, OSError):
            continue
    return CandidateRepo(
        slug=slug or root.name,
        owner=owner or "",
        files=files,
        created_at=created_at if created_at is not None else _earliest_commit_date(root),
    )
