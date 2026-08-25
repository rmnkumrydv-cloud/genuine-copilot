"""Deterministic signal engines (spec §6). No LLM, no ML opinion — every
originality judgment in the product is made here.
"""

from __future__ import annotations

from .clone import CandidateRepo, CloneResult, detect_clones
from .commit_forensics import CommitForensics, analyze_commits
from .matchers import DEFAULT_MATCHER, CloneMatcher, StdlibCloneMatcher
from .readme_consistency import ReadmeResult, analyze_readme
from .registry import RegistryResult
from .registry import check as registry_check
from .registry import register as registry_register

__all__ = [
    "analyze_commits",
    "CommitForensics",
    "detect_clones",
    "CandidateRepo",
    "CloneResult",
    "CloneMatcher",
    "StdlibCloneMatcher",
    "DEFAULT_MATCHER",
    "analyze_readme",
    "ReadmeResult",
    "registry_check",
    "registry_register",
    "RegistryResult",
]
