"""Pluggable clone-matcher interface (spec §6.3).

The deterministic stdlib matcher is the default and the one the pipeline ships
with. ``copydetect`` / JPlag / SourcererCC slot in behind the same interface for
the Gate-2 benchmark ("keep whichever catches restructured Type-3/4 clones
better") without touching the repo-level orchestration in ``clone.py``.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from .similarity import FileComparison, compare_generic, compare_python


@runtime_checkable
class CloneMatcher(Protocol):
    name: str

    def compare_files(self, a_src: str, b_src: str, language: str) -> FileComparison:
        ...


class StdlibCloneMatcher:
    """Default: pure-stdlib AST + token similarity. Deterministic, no deps."""

    name = "stdlib-ast"

    def compare_files(self, a_src: str, b_src: str, language: str) -> FileComparison:
        if language == "python":
            return compare_python(a_src, b_src)
        return compare_generic(a_src, b_src)


class CopydetectMatcher:
    """Adapter for the ``copydetect`` benchmark option (§6.3).

    Kept thin and lazy so the core install/runtime never depends on it. Wire this
    in during Gate 2 to benchmark against the stdlib matcher on the fixture set.
    """

    name = "copydetect"

    def compare_files(self, a_src: str, b_src: str, language: str) -> FileComparison:  # pragma: no cover
        raise NotImplementedError(
            "CopydetectMatcher is a Gate-2 benchmark adapter and is not wired yet. "
            "Use StdlibCloneMatcher (the default) for the core pipeline."
        )


DEFAULT_MATCHER: CloneMatcher = StdlibCloneMatcher()
