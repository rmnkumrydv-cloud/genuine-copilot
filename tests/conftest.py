"""Shared test fixtures.

The ``make_git_repo`` factory builds real, tiny git repositories with fully
controlled commit histories (message, timestamp, files) so the commit-forensics
and integration tests exercise the actual gitpython ingestion path rather than
hand-mocked commit objects.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from git import Actor, Repo

FIXTURES = Path(__file__).parent / "fixtures"


def read_fixture(rel: str) -> str:
    return (FIXTURES / rel).read_text(encoding="utf-8")


@pytest.fixture
def tmp_db(tmp_path) -> Path:
    return tmp_path / "test.sqlite"


@pytest.fixture
def cache_root(tmp_path) -> Path:
    d = tmp_path / "clones"
    d.mkdir()
    return d


@pytest.fixture
def make_git_repo(tmp_path):
    """Factory: make_git_repo(name, commits) -> Path.

    ``commits`` is a list of dicts: {"message", "files": {path: content}, "date"}.
    ``date`` is a git-style timestamp string, e.g. "2023-06-01 12:00:00 +0000".
    Both author and commit dates are set to it (mirroring fake-git-history, which
    stamps both).
    """
    counter = {"n": 0}

    def _make(name: str, commits: list[dict]) -> Path:
        counter["n"] += 1
        root = tmp_path / f"{name}_{counter['n']}"
        root.mkdir()
        repo = Repo.init(root)
        actor = Actor("Test Dev", "dev@example.com")
        for spec in commits:
            for rel, content in spec.get("files", {}).items():
                fp = root / rel
                fp.parent.mkdir(parents=True, exist_ok=True)
                fp.write_text(content, encoding="utf-8")
                repo.index.add([str(fp)])
            date = spec.get("date")
            repo.index.commit(
                spec.get("message", "commit"),
                author=actor,
                committer=actor,
                author_date=date,
                commit_date=date,
            )
        return root

    return _make
