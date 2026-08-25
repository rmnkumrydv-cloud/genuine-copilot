"""Whole-repo MinHash fingerprint (spec §4 "Scaling", §6.4).

Cheap, order-insensitive similarity signal computed in seconds. Two uses:

1. A fast pre-filter before expensive per-file AST comparison.
2. The stored value in the shared registry (§6.4) — new submissions are checked
   for near-duplicates against every past submission's fingerprint.

Uses ``datasketch`` MinHash. Fingerprints are stored as a plain ``list[int]`` so
they round-trip through JSON/SQLite without pickling.
"""

from __future__ import annotations

from datasketch import MinHash

from ..textutil import shingles, word_tokens

NUM_PERM = 128
SHINGLE_K = 5


def build_minhash(texts: list[str], num_perm: int = NUM_PERM) -> MinHash:
    """MinHash over the union of k-gram shingles across all given file texts."""
    mh = MinHash(num_perm=num_perm)
    seen = False
    for text in texts:
        for sh in shingles(word_tokens(text), SHINGLE_K):
            mh.update(sh.encode("utf-8"))
            seen = True
    if not seen:
        # Empty repo — hash a sentinel so the signature is stable, not garbage.
        mh.update(b"\x00__genuine_empty__")
    return mh


def signature(mh: MinHash) -> list[int]:
    return [int(x) for x in mh.hashvalues]


def from_signature(sig: list[int], num_perm: int = NUM_PERM) -> MinHash:
    import numpy as np

    return MinHash(num_perm=num_perm, hashvalues=np.array(sig, dtype=np.uint64))


def estimated_jaccard(sig_a: list[int], sig_b: list[int]) -> float:
    """Estimated Jaccard similarity between two stored signatures, in [0, 1]."""
    if not sig_a or not sig_b or len(sig_a) != len(sig_b):
        return 0.0
    matches = sum(1 for a, b in zip(sig_a, sig_b) if a == b)
    return matches / len(sig_a)
