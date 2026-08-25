"""Language detection and file-exclusion heuristics (spec §6.2).

Exclusion keeps vendored, generated, test, and lockfile noise out of both the
significance ranking and the clone comparison — otherwise a copied `node_modules`
or an identical `package-lock.json` would dominate the similarity signal and
every repo would look like a clone of every other.
"""

from __future__ import annotations

import re
from pathlib import PurePosixPath

# Extension -> language label. Kept deliberately small; unknown = "unknown".
EXT_LANGUAGE: dict[str, str] = {
    ".py": "python",
    ".js": "javascript",
    ".jsx": "javascript",
    ".mjs": "javascript",
    ".cjs": "javascript",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".java": "java",
    ".go": "go",
    ".rb": "ruby",
    ".rs": "rust",
    ".c": "c",
    ".h": "c",
    ".cpp": "cpp",
    ".cc": "cpp",
    ".hpp": "cpp",
    ".cs": "csharp",
    ".php": "php",
    ".kt": "kotlin",
    ".swift": "swift",
    ".scala": "scala",
    ".sh": "shell",
}

# Directory names that mark vendored / generated / build output. Matched on any
# path segment (case-insensitive).
EXCLUDED_DIRS: frozenset[str] = frozenset(
    {
        "node_modules",
        "vendor",
        "third_party",
        "thirdparty",
        "external",
        "deps",
        "dist",
        "build",
        "out",
        "target",  # rust/java build output
        ".next",
        ".nuxt",
        "site-packages",
        "__pycache__",
        ".venv",
        "venv",
        "env",
        ".git",
        "migrations",  # usually framework-generated
        "generated",
        "gen",
        "bower_components",
        ".gradle",
        "coverage",
        "htmlcov",
    }
)

# Exact filenames that are lockfiles / generated manifests.
EXCLUDED_FILENAMES: frozenset[str] = frozenset(
    {
        "package-lock.json",
        "yarn.lock",
        "pnpm-lock.yaml",
        "poetry.lock",
        "pipfile.lock",
        "composer.lock",
        "cargo.lock",
        "go.sum",
        "gemfile.lock",
    }
)

# Filename patterns for generated code and tests.
_GENERATED_PATTERNS = [
    re.compile(r".*\.min\.(js|css)$", re.I),
    re.compile(r".*\.bundle\.js$", re.I),
    re.compile(r".*_pb2\.py$", re.I),
    re.compile(r".*\.pb\.go$", re.I),
    re.compile(r".*\.g\.dart$", re.I),
    re.compile(r".*\.freezed\.dart$", re.I),
    re.compile(r".*\.generated\..*$", re.I),
    re.compile(r".*\.designer\.cs$", re.I),
]

_TEST_PATTERNS = [
    re.compile(r"(^|/)test_[^/]+\.py$", re.I),
    re.compile(r".*_test\.(py|go|js|ts)$", re.I),
    re.compile(r".*\.(test|spec)\.(js|jsx|ts|tsx)$", re.I),
    re.compile(r".*Test\.(java|kt|scala)$"),
]

_TEST_DIRS = frozenset({"test", "tests", "spec", "specs", "__tests__", "testdata"})


def detect_language(path: str) -> str:
    return EXT_LANGUAGE.get(PurePosixPath(path).suffix.lower(), "unknown")


def classify_exclusion(path: str) -> str:
    """Return an exclusion reason, or "" if the file should be kept.

    Reasons: ``vendor`` | ``generated`` | ``test`` | ``lockfile`` | ``non_code``.
    """
    p = PurePosixPath(path.replace("\\", "/"))
    segments = {seg.lower() for seg in p.parts}

    if segments & EXCLUDED_DIRS:
        return "vendor"
    if p.name.lower() in EXCLUDED_FILENAMES:
        return "lockfile"
    if any(pat.match(str(p)) for pat in _GENERATED_PATTERNS):
        return "generated"
    if (segments & _TEST_DIRS) or any(pat.search(str(p)) for pat in _TEST_PATTERNS):
        return "test"
    if detect_language(path) == "unknown":
        return "non_code"
    return ""


def count_loc(text: str) -> int:
    """Non-blank physical lines. Deterministic and language-agnostic."""
    return sum(1 for line in text.splitlines() if line.strip())
