"""Heavily-rewritten fixture: solves the *same problem* as the original but with
genuinely different structure — dict-of-dicts instead of dataclasses, different
control flow, different decomposition. A Type-4 "same behavior, new code" case.

Should score MEANINGFULLY LOWER on logic similarity than the renamed copy — this
is the ordering the clone detector must preserve (spec §8.1).
"""

from __future__ import annotations


class Warehouse:
    def __init__(self):
        self._rows = []  # list of [code, price, qty] triples — different shape entirely

    def _find(self, code):
        for idx, row in enumerate(self._rows):
            if row[0] == code:
                return idx
        return -1

    def stock(self, code, price, qty):
        pos = self._find(code)
        if pos >= 0:
            self._rows[pos][2] = self._rows[pos][2] + qty
            return
        self._rows.append([code, price, qty])

    def ship(self, code, qty):
        pos = self._find(code)
        if pos < 0 or self._rows[pos][2] - qty < 0:
            raise ValueError("cannot ship")
        self._rows[pos][2] -= qty

    def valuation(self):
        acc = 0.0
        for row in self._rows:
            acc = acc + row[1] * row[2]
        return acc

    def needs_reorder(self, minimum):
        result = []
        i = 0
        while i < len(self._rows):
            if self._rows[i][2] < minimum:
                result.append(self._rows[i][0])
            i += 1
        return result
