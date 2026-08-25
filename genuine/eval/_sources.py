"""Self-contained source bodies for the evaluation corpus (Gate 7, spec §8.3).

These are small, realistic Python modules with *known relationships* to each
other, so the labeled dataset in :mod:`genuine.eval.dataset` can be built with no
network and no dependency on ``tests/`` — the eval harness ships as library code.

The relationships are the whole point (they mirror the §8.4 regression cases):

* ``INVENTORY`` vs ``INVENTORY_RENAMED`` — identical structure, identifiers
  renamed only → **high logic similarity** (a copy that survives renaming).
* ``INVENTORY`` vs ``WAREHOUSE`` — same problem domain, independent
  implementation (functions+tuples vs dataclasses) → **low logic similarity**
  (an honest rewrite must score clean even against an older similar repo).
* ``FLASK_A`` vs ``FLASK_B`` — the same framework skeleton, different handler
  logic → **high structural, low logic** (shared boilerplate is not a clone).

The remaining modules are distinct, unrelated programs used as clean originals.
"""

from __future__ import annotations

# --------------------------------------------------------------------------- #
# The clone pair: a program and a pure-rename copy of it                       #
# --------------------------------------------------------------------------- #
INVENTORY = '''\
"""A tiny in-memory inventory ledger."""

from dataclasses import dataclass, field


@dataclass
class Item:
    sku: str
    quantity: int = 0
    reorder_at: int = 5


@dataclass
class Inventory:
    items: dict = field(default_factory=dict)

    def add(self, sku, quantity):
        if sku not in self.items:
            self.items[sku] = Item(sku)
        self.items[sku].quantity += quantity
        return self.items[sku].quantity

    def remove(self, sku, quantity):
        if sku not in self.items:
            raise KeyError(sku)
        item = self.items[sku]
        if quantity > item.quantity:
            raise ValueError("not enough stock")
        item.quantity -= quantity
        return item.quantity

    def low_stock(self):
        result = []
        for item in self.items.values():
            if item.quantity <= item.reorder_at:
                result.append(item.sku)
        return sorted(result)
'''

# Same structure as INVENTORY, identifiers renamed only. The logic-similarity
# metric normalizes identifiers away, so this scores as a near-perfect copy.
INVENTORY_RENAMED = '''\
"""Stock keeping helper."""

from dataclasses import dataclass, field


@dataclass
class Product:
    code: str
    count: int = 0
    threshold: int = 5


@dataclass
class Ledger:
    products: dict = field(default_factory=dict)

    def deposit(self, code, count):
        if code not in self.products:
            self.products[code] = Product(code)
        self.products[code].count += count
        return self.products[code].count

    def withdraw(self, code, count):
        if code not in self.products:
            raise KeyError(code)
        entry = self.products[code]
        if count > entry.count:
            raise ValueError("not enough stock")
        entry.count -= count
        return entry.count

    def below_threshold(self):
        out = []
        for entry in self.products.values():
            if entry.count <= entry.threshold:
                out.append(entry.code)
        return sorted(out)
'''

# Same domain as INVENTORY, independent implementation → low logic similarity.
WAREHOUSE = '''\
"""Warehouse stock tracker built on plain dicts and functions."""


def make_store():
    return {}


def receive(store, sku, qty):
    have, limit = store.get(sku, (0, 5))
    store[sku] = (have + qty, limit)
    return store[sku][0]


def ship(store, sku, qty):
    if sku not in store:
        raise KeyError(sku)
    have, limit = store[sku]
    if qty > have:
        raise ValueError("insufficient")
    store[sku] = (have - qty, limit)
    return have - qty


def needs_reorder(store):
    flagged = [sku for sku, (have, limit) in store.items() if have <= limit]
    return sorted(flagged)
'''

# --------------------------------------------------------------------------- #
# The boilerplate pair: shared Flask skeleton, different handler logic         #
# --------------------------------------------------------------------------- #
FLASK_A = '''\
"""Minimal Flask numeric service."""

from flask import Flask, jsonify, request

app = Flask(__name__)


@app.route("/health")
def health():
    return jsonify(status="ok")


@app.route("/compute", methods=["POST"])
def compute():
    data = request.get_json()
    numbers = data.get("numbers", [])
    total = 0
    for value in numbers:
        total += value
    return jsonify(sum=total, count=len(numbers))


if __name__ == "__main__":
    app.run()
'''

FLASK_B = '''\
"""Minimal Flask text service."""

from flask import Flask, jsonify, request

app = Flask(__name__)


@app.route("/health")
def health():
    return jsonify(status="ok")


@app.route("/analyze", methods=["POST"])
def analyze():
    data = request.get_json()
    words = data.get("text", "").split()
    longest = ""
    for word in words:
        if len(word) > len(longest):
            longest = word
    return jsonify(words=len(words), longest=longest)


if __name__ == "__main__":
    app.run()
'''

# --------------------------------------------------------------------------- #
# Distinct, unrelated originals                                                #
# --------------------------------------------------------------------------- #
CSV_REPORT = '''\
"""Summarize a CSV of sales into per-region totals."""

import csv
from collections import defaultdict


def load(path):
    with open(path, newline="") as fh:
        return list(csv.DictReader(fh))


def totals_by_region(rows):
    totals = defaultdict(float)
    for row in rows:
        totals[row["region"]] += float(row["amount"])
    return dict(totals)


def top_region(rows):
    totals = totals_by_region(rows)
    if not totals:
        return None
    return max(totals, key=totals.get)
'''

LRU_CACHE = '''\
"""A small LRU cache using an ordered dict."""

from collections import OrderedDict


class LRUCache:
    def __init__(self, capacity):
        self.capacity = capacity
        self.store = OrderedDict()

    def get(self, key):
        if key not in self.store:
            return None
        self.store.move_to_end(key)
        return self.store[key]

    def put(self, key, value):
        self.store[key] = value
        self.store.move_to_end(key)
        if len(self.store) > self.capacity:
            self.store.popitem(last=False)
'''

GRAPH_BFS = '''\
"""Breadth-first shortest path on an unweighted graph."""

from collections import deque


def shortest_path(graph, start, goal):
    seen = {start}
    queue = deque([(start, [start])])
    while queue:
        node, path = queue.popleft()
        if node == goal:
            return path
        for nxt in graph.get(node, []):
            if nxt not in seen:
                seen.add(nxt)
                queue.append((nxt, path + [nxt]))
    return None
'''

RATE_LIMITER = '''\
"""Token-bucket rate limiter."""

import time


class TokenBucket:
    def __init__(self, rate, capacity):
        self.rate = rate
        self.capacity = capacity
        self.tokens = capacity
        self.updated = time.monotonic()

    def allow(self, cost=1):
        now = time.monotonic()
        self.tokens = min(self.capacity, self.tokens + (now - self.updated) * self.rate)
        self.updated = now
        if self.tokens >= cost:
            self.tokens -= cost
            return True
        return False
'''

MARKDOWN_TOC = '''\
"""Generate a table of contents from markdown headings."""

import re

HEADING = re.compile(r"^(#+)\\s+(.*)$")


def extract_headings(text):
    out = []
    for line in text.splitlines():
        match = HEADING.match(line)
        if match:
            out.append((len(match.group(1)), match.group(2).strip()))
    return out


def render_toc(text):
    lines = []
    for level, title in extract_headings(text):
        slug = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")
        lines.append("  " * (level - 1) + f"- [{title}](#{slug})")
    return "\\n".join(lines)
'''

FIB = '''\
"""Iterative Fibonacci."""


def fib(n):
    a, b = 0, 1
    for _ in range(n):
        a, b = b, a + b
    return a
'''
