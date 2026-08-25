"""Turn a local git working copy into a :class:`RepoAnalysis` (spec §6.1).

This is pure local git parsing (``gitpython``) plus the significance/coverage
pass. No originality judgment happens here — it only assembles the evidence
substrate the deterministic signals run on.
"""

from __future__ import annotations

from datetime import timezone
from pathlib import Path
from typing import Optional

from git import Repo

from ..models import CommitRecord, DiffStats, FileRecord, RepoAnalysis
from .fingerprint import build_minhash, signature
from .github import RepoRef, clone_or_open, fetch_github_metadata, parse_repo_url, utcnow
from .languages import classify_exclusion, count_loc, detect_language
from .significance import compute_coverage, rank_files

# Hard caps so a pathological repo can't wedge the pipeline. Surfaced, not silent.
MAX_COMMITS = 2000
MAX_FILE_BYTES = 1_000_000  # 1 MB — anything larger is data/asset, not logic
MAX_FILES = 5000


def _read_commits(repo: Repo, default_branch: str) -> list[CommitRecord]:
    records: list[CommitRecord] = []
    try:
        commits = list(repo.iter_commits(max_count=MAX_COMMITS))
    except Exception:  # empty repo / no HEAD
        return records

    for c in commits:
        stats = c.stats.total
        ts = c.committed_datetime
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        records.append(
            CommitRecord(
                sha=c.hexsha,
                timestamp=ts,
                message=(c.message or "").strip() if isinstance(c.message, str) else "",
                author_email=(c.author.email or "") if c.author else "",
                diff_stats=DiffStats(
                    additions=stats.get("insertions", 0),
                    deletions=stats.get("deletions", 0),
                    files_changed=stats.get("files", 0),
                ),
            )
        )
    return records


def _read_files(root: Path) -> tuple[list[FileRecord], dict[str, str]]:
    """Walk the working tree. Returns (records, {path: text}) for includable
    files. Excluded files still get a record (for the UI) but no text/LOC work.
    """
    records: list[FileRecord] = []
    texts: dict[str, str] = {}
    count = 0

    for path in sorted(root.rglob("*")):
        if count >= MAX_FILES:
            break
        if not path.is_file() or ".git" in path.parts:
            continue
        rel = path.relative_to(root).as_posix()
        count += 1

        reason = classify_exclusion(rel)
        if reason:
            records.append(
                FileRecord(path=rel, language=detect_language(rel), excluded=True, exclude_reason=reason)
            )
            continue

        try:
            if path.stat().st_size > MAX_FILE_BYTES:
                records.append(
                    FileRecord(path=rel, language=detect_language(rel), excluded=True, exclude_reason="too_large")
                )
                continue
            text = path.read_text(encoding="utf-8", errors="strict")
        except (UnicodeDecodeError, OSError):
            # Binary or unreadable — not logic we can compare.
            records.append(
                FileRecord(path=rel, language=detect_language(rel), excluded=True, exclude_reason="binary")
            )
            continue

        texts[rel] = text
        records.append(
            FileRecord(path=rel, language=detect_language(rel), loc=count_loc(text), excluded=False)
        )
    return records, texts


def _read_readme(root: Path) -> str:
    for name in ("README.md", "README.rst", "README.txt", "README", "readme.md"):
        p = root / name
        if p.is_file():
            try:
                return p.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                return ""
    return ""


def ingest_local(
    path: str | Path,
    repo_url: str = "",
    ref: Optional[RepoRef] = None,
    metadata: Optional[dict] = None,
    top_k: int = 40,
) -> RepoAnalysis:
    """Build a RepoAnalysis from a local working copy. The network-free core."""
    root = Path(path).resolve()
    metadata = metadata or {}
    default_branch = metadata.get("default_branch", "main")

    try:
        repo = Repo(str(root))
        commits = _read_commits(repo, default_branch)
    except Exception:
        commits = []  # a plain directory with no git history is still analyzable

    # repo_created_at: prefer GitHub's value; otherwise fall back to the earliest
    # commit date. This proxy is what makes the temporal-direction check (§8.4-5)
    # work for local/offline analysis, where no API metadata is available.
    repo_created_at = metadata.get("repo_created_at")
    if repo_created_at is None and commits:
        repo_created_at = min(c.timestamp for c in commits)

    files, texts = _read_files(root)
    rank_files(files, texts, top_k=top_k)
    total_loc, compared_loc, coverage = compute_coverage(files)

    # Fingerprint over the ranked (significant) files only — the same logic the
    # clone signal compares — so the registry duplicate check is apples-to-apples.
    ranked_paths = [f.path for f in files if f.significance_rank > 0]
    fp = signature(build_minhash([texts[p] for p in ranked_paths if p in texts]))

    return RepoAnalysis(
        repo_url=repo_url or str(root),
        owner=ref.owner if ref else "",
        repo_name=ref.name if ref else root.name,
        default_branch=default_branch,
        ingested_at=utcnow(),
        repo_created_at=repo_created_at,
        commits=commits,
        files=files,
        readme_text=_read_readme(root),
        total_loc=total_loc,
        compared_loc=compared_loc,
        coverage_ratio=coverage,
        fingerprint=fp,
    )


def ingest(url_or_path: str, cache_root: Path, token: str = "", top_k: int = 40) -> RepoAnalysis:
    """Top-level entry: accepts a local path or a remote URL.

    * Local existing directory  → parsed in place (offline).
    * Remote URL                → metadata fetch (best-effort) + clone into cache.
    """
    p = Path(url_or_path)
    if p.exists() and p.is_dir():
        return ingest_local(p, repo_url=str(p.resolve()), top_k=top_k)

    ref = parse_repo_url(url_or_path)
    if ref is None:
        raise ValueError(f"Not a local directory or a recognizable repo URL: {url_or_path!r}")

    metadata = fetch_github_metadata(ref, token=token)
    local_path = clone_or_open(ref, cache_root, token=token)
    return ingest_local(local_path, repo_url=url_or_path, ref=ref, metadata=metadata, top_k=top_k)
