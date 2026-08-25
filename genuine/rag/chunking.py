"""Split source files into retrievable code regions.

Python files are chunked by top-level structure (module-level code and each
top-level ``def``/``class`` become their own region) so a retrieved hit points
at a real, self-contained span. Everything else — manifests, JS/TS, unparseable
Python — falls back to overlapping fixed-size line windows. Every chunk carries
a 1-based ``path:start-end`` citation.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass

# Fallback line-window geometry (non-Python / unparseable).
_WINDOW = 50
_OVERLAP = 10


@dataclass(frozen=True)
class CodeChunk:
    path: str
    start_line: int  # 1-based, inclusive
    end_line: int  # 1-based, inclusive
    text: str
    symbol: str = ""  # def/class name, "<module>", or "" for a window

    @property
    def citation(self) -> str:
        """Human/UI-safe reference — a location, never raw content."""
        return f"{self.path}:{self.start_line}-{self.end_line}"


def _window_chunks(path: str, lines: list[str]) -> list[CodeChunk]:
    if not any(ln.strip() for ln in lines):
        return []
    stride = max(1, _WINDOW - _OVERLAP)
    chunks: list[CodeChunk] = []
    for start in range(0, len(lines), stride):
        window = lines[start : start + _WINDOW]
        if not any(ln.strip() for ln in window):
            continue
        chunks.append(
            CodeChunk(
                path=path,
                start_line=start + 1,
                end_line=start + len(window),
                text="\n".join(window),
            )
        )
        if start + _WINDOW >= len(lines):
            break
    return chunks


def _node_start(node: ast.AST) -> int:
    """Start line including any decorators (which precede ``node.lineno``)."""
    decorators = getattr(node, "decorator_list", [])
    lines = [node.lineno] + [d.lineno for d in decorators]
    return min(lines)


def _python_chunks(path: str, text: str, lines: list[str]) -> list[CodeChunk] | None:
    try:
        tree = ast.parse(text)
    except (SyntaxError, ValueError):
        return None  # signal: caller should use the window fallback

    chunks: list[CodeChunk] = []
    buf: list[tuple[int, int]] = []  # spans of consecutive module-level statements

    def flush() -> None:
        if not buf:
            return
        start, end = buf[0][0], buf[-1][1]
        body = "\n".join(lines[start - 1 : end])
        if body.strip():
            chunks.append(CodeChunk(path, start, end, body, symbol="<module>"))
        buf.clear()

    for node in tree.body:
        start = _node_start(node)
        end = getattr(node, "end_lineno", node.lineno) or node.lineno
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            flush()
            body = "\n".join(lines[start - 1 : end])
            chunks.append(CodeChunk(path, start, end, body, symbol=node.name))
        else:
            buf.append((start, end))
    flush()

    # A file that's all imports/constants (no def/class) yields one module chunk;
    # if even that came back empty, treat as unparseable-ish and window it.
    return chunks or None


def chunk_file(path: str, text: str) -> list[CodeChunk]:
    """Chunk one file into retrievable regions (never raises)."""
    lines = text.splitlines()
    if not lines:
        return []
    if path.endswith(".py"):
        py = _python_chunks(path, text, lines)
        if py is not None:
            return py
    return _window_chunks(path, lines)


def chunk_repo(texts: dict[str, str]) -> list[CodeChunk]:
    """Chunk every file, in deterministic path order."""
    chunks: list[CodeChunk] = []
    for path in sorted(texts):
        chunks.extend(chunk_file(path, texts[path]))
    return chunks
