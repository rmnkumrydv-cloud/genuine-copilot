"""Resolve a repo URL (or local path) to a local working copy + metadata.

Ingestion is offline-friendly by design: a local directory is used as-is (that's
how fixtures and the eval set run without the network), and GitHub metadata is
best-effort — if there's no token or no network, we fall back to git-derived
values instead of failing the whole analysis.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import requests
from git import GitCommandError, Repo

_URL_RE = re.compile(
    r"^(?:https?://|git@)(?P<host>[^/:]+)[/:](?P<owner>[^/]+)/(?P<name>[^/]+?)(?:\.git)?/?$"
)


class RepoRef:
    def __init__(self, host: str, owner: str, name: str):
        self.host = host
        self.owner = owner
        self.name = name

    @property
    def slug(self) -> str:
        return f"{self.owner}/{self.name}"


def parse_repo_url(url: str) -> Optional[RepoRef]:
    m = _URL_RE.match(url.strip())
    if not m:
        return None
    return RepoRef(m.group("host"), m.group("owner"), m.group("name"))


def fetch_github_metadata(ref: RepoRef, token: str = "") -> dict:
    """Best-effort repo metadata. Returns {} on any failure (no network/auth)."""
    if "github.com" not in ref.host:
        return {}
    headers = {"Accept": "application/vnd.github+json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    try:
        resp = requests.get(
            f"https://api.github.com/repos/{ref.owner}/{ref.name}",
            headers=headers,
            timeout=10,
        )
        if resp.status_code != 200:
            return {}
        data = resp.json()
        created = data.get("created_at")
        return {
            "repo_created_at": datetime.fromisoformat(created.replace("Z", "+00:00"))
            if created
            else None,
            "default_branch": data.get("default_branch", "main"),
        }
    except (requests.RequestException, ValueError):
        return {}


def clone_or_open(ref: RepoRef, dest_root: Path, token: str = "") -> Path:
    """Clone the repo under ``dest_root`` (full history — commit forensics needs
    it), or open the existing clone if already present. Returns the local path.
    """
    dest = dest_root / ref.host / ref.owner / ref.name
    if (dest / ".git").exists():
        return dest
    dest.parent.mkdir(parents=True, exist_ok=True)

    clone_url = f"https://{ref.host}/{ref.owner}/{ref.name}.git"
    if token and "github.com" in ref.host:
        clone_url = f"https://{token}@{ref.host}/{ref.owner}/{ref.name}.git"
    try:
        Repo.clone_from(clone_url, str(dest))
    except GitCommandError as exc:  # pragma: no cover - network dependent
        raise RuntimeError(f"git clone failed for {ref.slug}: {exc.stderr or exc}") from exc
    return dest


def utcnow() -> datetime:
    return datetime.now(timezone.utc)
