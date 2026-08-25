"""Significance ranking and coverage (spec §6.2).

Large repos can't get an expensive AST comparison on every file, so we rank
files by ``LOC × import-centrality`` and only deep-compare the top-K. The
fraction of includable logic that top-K covers is the ``coverage_ratio`` — and a
clean score computed over low coverage is downgraded to ``insufficient_signal``
by the scoring gate, so the number is load-bearing, not decorative.
"""

from __future__ import annotations

import ast
from pathlib import PurePosixPath

from ..models import FileRecord

# Weighting of the two significance components. LOC says "how much logic is
# here"; centrality says "how much the rest of the repo leans on it". A tiny
# file everything imports (e.g. core models) still ranks high.
_W_LOC = 0.6
_W_CENTRALITY = 0.4


def _module_name(path: str) -> str | None:
    p = PurePosixPath(path)
    if p.suffix != ".py":
        return None
    parts = list(p.parts)
    if parts[-1] == "__init__.py":
        parts = parts[:-1]
    else:
        parts[-1] = p.stem
    return ".".join(parts) if parts else None


def _import_centrality(texts: dict[str, str]) -> dict[str, float]:
    """Fraction of *other* Python files that import each Python file.

    Best-effort static resolution: exact dotted module, any dotted prefix, or a
    bare final-component stem. Approximate by design — it only steers ranking,
    it is never itself a verdict signal.
    """
    py_files = [p for p in texts if p.endswith(".py")]
    module_to_file: dict[str, str] = {}
    stem_to_files: dict[str, list[str]] = {}
    for path in py_files:
        mod = _module_name(path)
        if not mod:
            continue
        module_to_file[mod] = path
        stem_to_files.setdefault(mod.split(".")[-1], []).append(path)

    importers: dict[str, set[str]] = {p: set() for p in py_files}

    def _resolve(target: str) -> list[str]:
        if target in module_to_file:
            return [module_to_file[target]]
        # longest known dotted prefix
        parts = target.split(".")
        for i in range(len(parts), 0, -1):
            prefix = ".".join(parts[:i])
            if prefix in module_to_file:
                return [module_to_file[prefix]]
        return stem_to_files.get(parts[-1], [])

    for path in py_files:
        try:
            tree = ast.parse(texts[path])
        except (SyntaxError, ValueError):
            continue
        targets: list[str] = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                targets += [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module:
                targets.append(node.module)
                targets += [f"{node.module}.{a.name}" for a in node.names]
        for tgt in targets:
            for resolved in _resolve(tgt):
                if resolved != path:
                    importers[resolved].add(path)

    denom = max(1, len(py_files) - 1)
    return {p: len(importers[p]) / denom for p in py_files}


def rank_files(files: list[FileRecord], texts: dict[str, str], top_k: int = 40) -> None:
    """Populate ``import_centrality``, ``significance_score`` and
    ``significance_rank`` (1 = most significant) on non-excluded files, in place.
    Only the top-K get a positive rank; the rest stay at 0 (not deep-compared).
    """
    centrality = _import_centrality(texts)
    included = [f for f in files if not f.excluded]
    max_loc = max((f.loc for f in included), default=1) or 1

    for f in included:
        f.import_centrality = round(centrality.get(f.path, 0.0), 4)
        norm_loc = f.loc / max_loc
        f.significance_score = round(_W_LOC * norm_loc + _W_CENTRALITY * f.import_centrality, 4)

    # Deterministic ordering: score desc, then path asc to break ties stably.
    included.sort(key=lambda f: (-f.significance_score, f.path))
    for i, f in enumerate(included[:top_k], start=1):
        f.significance_rank = i


def compute_coverage(files: list[FileRecord]) -> tuple[int, int, float]:
    """Return ``(total_loc, compared_loc, coverage_ratio)``.

    * total_loc    — LOC across all includable (non-excluded) files.
    * compared_loc — LOC across the ranked top-K that get deep comparison.
    """
    total = sum(f.loc for f in files if not f.excluded)
    compared = sum(f.loc for f in files if not f.excluded and f.significance_rank > 0)
    ratio = round(compared / total, 4) if total else 0.0
    return total, compared, ratio
