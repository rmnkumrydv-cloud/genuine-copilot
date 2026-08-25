"""Clone / AST similarity — the highest-weight deterministic signal (spec §6.3).

Two axes reported **separately**, which is the whole point of the module:

* **structural_similarity** — the AST *skeleton*: statement/expression node types
  and nesting, with all identifiers and literals erased. Two files that share a
  framework's boilerplate shape (same imports, same ``if __name__`` guard, same
  class layout) score high here even when written independently.
* **logic_similarity** — the normalized *token stream* of function/statement
  bodies: keywords kept, every identifier folded to ``NAME`` and every literal to
  ``LIT``. This captures copied logic that survives cosmetic renaming, while
  staying blind to variable names.

The split is what lets the system honor regression case §8.4-2: *high structural
+ low logic → original* (legit boilerplate), whereas *high structural + high
logic → copied* (same skeleton AND same bodies).

Everything here is stdlib (``ast``, ``tokenize``, ``difflib``) — deterministic,
auditable, no ML. ``copydetect``/JPlag can be slotted in behind the same
:class:`CloneMatcher` interface for the Gate-2 benchmark (see ``matchers.py``).
"""

from __future__ import annotations

import ast
import io
import keyword
import tokenize
from dataclasses import dataclass

_PY_KEYWORDS = frozenset(keyword.kwlist)

# Token classes we keep verbatim in the logic stream (structure-bearing).
# NB: keywords are *not* a distinct tokenize type — they arrive as NAME tokens
# and are handled in the NAME branch of ``logic_tokens`` via ``_PY_KEYWORDS``.
_STRUCTURAL_TOKENS = frozenset(
    {tokenize.OP, tokenize.INDENT, tokenize.DEDENT, tokenize.NEWLINE}
)


# --------------------------------------------------------------------------- #
# Python-aware normalization                                                  #
# --------------------------------------------------------------------------- #
def ast_skeleton(source: str) -> list[str]:
    """Ordered list of AST node type names, identifiers/literals erased.

    ``a = foo(1)`` and ``result = bar(2)`` produce the *same* skeleton — so this
    axis measures shared structure, not shared naming.

    Traversal is **pre-order DFS**, not ``ast.walk``'s breadth-first order: the
    linearized stream follows source structure, so n-grams capture real
    parent→child / sibling shape and stay stable when an unrelated branch is
    added elsewhere in the file (BFS would smear that change across the level).
    """
    try:
        tree = ast.parse(source)
    except (SyntaxError, ValueError):
        return []
    out: list[str] = []
    stack = [tree]
    while stack:
        node = stack.pop()
        out.append(type(node).__name__)
        stack.extend(reversed(list(ast.iter_child_nodes(node))))
    return out


def logic_tokens(source: str) -> list[str]:
    """Normalized token stream: keywords kept, names→NAME, literals→LIT.

    Comments and whitespace are dropped, so reformatting and re-commenting a
    copied file does not lower its logic similarity.
    """
    out: list[str] = []
    try:
        toks = tokenize.generate_tokens(io.StringIO(source).readline)
        for tok in toks:
            if tok.type in (tokenize.COMMENT, tokenize.NL, tokenize.ENCODING, tokenize.ENDMARKER):
                continue
            if tok.type == tokenize.NAME:
                # keyword vs identifier
                out.append(tok.string if tok.string in _PY_KEYWORDS else "NAME")
            elif tok.type in (tokenize.NUMBER, tokenize.STRING, tokenize.FSTRING_START):
                out.append("LIT")
            elif tok.type in _STRUCTURAL_TOKENS:
                s = tok.string.strip()
                if s:
                    out.append(s)
    except (tokenize.TokenError, IndentationError, SyntaxError):
        # Fall back to a coarse whitespace split so we still return *something*.
        return [t for t in source.split() if t]
    return out


# --------------------------------------------------------------------------- #
# Similarity metrics                                                          #
#                                                                             #
# The two axes use deliberately *different* metrics because they answer        #
# different questions:                                                         #
#                                                                             #
# * structural — "do these files use the same kinds of constructs, in similar  #
#   proportion and local arrangement?" — an ORDER-INSENSITIVE multiset overlap #
#   of AST node types blended with short node-type n-grams. Shared framework   #
#   scaffolding scores high here regardless of what the bodies actually do.    #
# * logic — "is this the same code, modulo renaming?" — an ORDER-SENSITIVE     #
#   n-gram overlap of the normalized token stream blended with the longest     #
#   *contiguous* matching run. The contiguity term is what separates a real    #
#   copy (one long identical span) from boilerplate (many short shared glue    #
#   lines that a plain diff-ratio would happily add up to a high score).       #
# --------------------------------------------------------------------------- #
def _ngrams(seq: list[str], n: int) -> set[tuple[str, ...]]:
    if len(seq) < n:
        return {tuple(seq)} if seq else set()
    return {tuple(seq[i : i + n]) for i in range(len(seq) - n + 1)}


def jaccard(a: set, b: set) -> float:
    if not a and not b:
        return 0.0
    inter = len(a & b)
    union = len(a | b)
    return inter / union if union else 0.0


def _ngram_jaccard(a: list[str], b: list[str], n: int) -> float:
    return jaccard(_ngrams(a, n), _ngrams(b, n))


def multiset_overlap(a: list[str], b: list[str]) -> float:
    """Weighted Jaccard over element *counts* (∑min / ∑max). Order-insensitive:
    measures whether the same kinds of things appear in similar proportion."""
    from collections import Counter

    if not a or not b:
        return 0.0
    ca, cb = Counter(a), Counter(b)
    inter = sum((ca & cb).values())
    union = sum((ca | cb).values())
    return inter / union if union else 0.0


def longest_run_ratio(a: list[str], b: list[str]) -> float:
    """Length of the single longest contiguous matching run, over the shorter
    stream. 1.0 iff one stream is a contiguous slice of the other — the hallmark
    of a copy. Scattered short matches (shared boilerplate) score low here even
    when ``difflib``'s aggregate ratio would be high.
    """
    import difflib

    if not a or not b:
        return 0.0
    cap = 4000  # difflib is quadratic; cap keeps top-K comparison snappy.
    a, b = a[:cap], b[:cap]
    block = difflib.SequenceMatcher(None, a, b, autojunk=False).find_longest_match(
        0, len(a), 0, len(b)
    )
    return block.size / min(len(a), len(b))


def structural_similarity(a_skel: list[str], b_skel: list[str]) -> float:
    """Shared *shape*: half multiset overlap (construct vocabulary/proportion),
    half 3-gram overlap (local arrangement). In [0, 1]."""
    if not a_skel or not b_skel:
        return 0.0
    return round(0.5 * multiset_overlap(a_skel, b_skel) + 0.5 * _ngram_jaccard(a_skel, b_skel, 3), 4)


def logic_similarity(a_tok: list[str], b_tok: list[str]) -> float:
    """Copied-logic score: 0.6 n-gram overlap (robust to reordering) + 0.4
    longest contiguous run (rewards a genuine copied span). In [0, 1]."""
    if not a_tok or not b_tok:
        return 0.0
    return round(0.6 * _ngram_jaccard(a_tok, b_tok, 5) + 0.4 * longest_run_ratio(a_tok, b_tok), 4)


# --------------------------------------------------------------------------- #
# File-pair comparison                                                        #
# --------------------------------------------------------------------------- #
@dataclass
class FileComparison:
    structural_similarity: float
    logic_similarity: float
    matched_span: tuple[int, int]


def compare_python(a_src: str, b_src: str) -> FileComparison:
    struct = structural_similarity(ast_skeleton(a_src), ast_skeleton(b_src))
    logic = logic_similarity(logic_tokens(a_src), logic_tokens(b_src))
    span = _longest_matched_span(a_src, b_src)
    return FileComparison(structural_similarity=struct, logic_similarity=logic, matched_span=span)


def compare_generic(a_src: str, b_src: str) -> FileComparison:
    """Language-agnostic fallback for non-Python files: no AST is available, so
    both axes run on the whitespace-token stream (structural ≈ logic here).
    """
    from ..textutil import word_tokens

    a_tok = word_tokens(a_src)
    b_tok = word_tokens(b_src)
    logic = logic_similarity(a_tok, b_tok)
    # Without an AST, "structure" degrades to the same token evidence as logic.
    struct = round(0.5 * multiset_overlap(a_tok, b_tok) + 0.5 * _ngram_jaccard(a_tok, b_tok, 3), 4)
    return FileComparison(
        structural_similarity=struct, logic_similarity=logic, matched_span=_longest_matched_span(a_src, b_src)
    )


def _longest_matched_span(a_src: str, b_src: str) -> tuple[int, int]:
    """Longest matching block of a_src against b_src, as (start_line, end_line)
    in a_src (1-indexed). Used to point the UI/diff viewer at the copied region.
    """
    import difflib

    a_lines = a_src.splitlines()
    b_lines = b_src.splitlines()
    if not a_lines or not b_lines:
        return (0, 0)
    sm = difflib.SequenceMatcher(None, a_lines[:2000], b_lines[:2000], autojunk=False)
    block = sm.find_longest_match(0, min(len(a_lines), 2000), 0, min(len(b_lines), 2000))
    if block.size == 0:
        return (0, 0)
    return (block.a + 1, block.a + block.size)
