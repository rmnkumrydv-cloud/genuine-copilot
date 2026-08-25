"""Repo ingestion (spec §6.1-6.2)."""

from __future__ import annotations

from .fingerprint import build_minhash, estimated_jaccard, from_signature, signature
from .github import RepoRef, clone_or_open, fetch_github_metadata, parse_repo_url
from .repo import ingest, ingest_local
from .significance import compute_coverage, rank_files

__all__ = [
    "ingest",
    "ingest_local",
    "rank_files",
    "compute_coverage",
    "build_minhash",
    "signature",
    "from_signature",
    "estimated_jaccard",
    "parse_repo_url",
    "fetch_github_metadata",
    "clone_or_open",
    "RepoRef",
]
