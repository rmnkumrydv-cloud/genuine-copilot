"""The labeled evaluation corpus + tuning/held-out split (spec §8.3, Gate 7).

Every entry carries a ground-truth ``category`` (``original`` = authentic;
``copied`` / ``faked`` = inauthentic) and a ``split``:

* **tuning** — the only repos you may look at while adjusting ``rules.yaml``.
* **heldout** — touched once, at report time; the committed metrics come from
  here and here alone (spec §8.4-6 leakage check).

The corpus is *synthetic on purpose*: it is fully offline, deterministic, and
reproducible, and every case is constructed from the known-relationship sources
in :mod:`genuine.eval._sources` so the ground-truth labels are unarguable. Real
public-repo expansion is roadmap (see docs/evaluation.md).

`_healthy` builds an irregular, human-looking history; `_faked` builds the
regular-interval / fixed-time / canned-message history that tools like
``fake-git-history`` produce — the commit-forensics signal separates the two, and
the clone signal is what actually flags a faked repo that wraps copied code.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from typing import Optional

from . import _sources as S

ORIGINAL = "original"
COPIED = "copied"
FAKED = "faked"
CATEGORIES = (ORIGINAL, COPIED, FAKED)

TUNING = "tuning"
HELDOUT = "heldout"

# All candidates are dated well before any target's earliest commit, so the
# temporal-direction check reads "target likely copied" (spec §6.3, §8.4-5).
_CANDIDATE_BIRTH = datetime(2021, 1, 1, tzinfo=timezone.utc)


@dataclass
class CandidateSpec:
    """A predating repo to compare the target against (the 'original')."""

    slug: str
    owner: str
    files: dict[str, str]
    created_at: datetime = _CANDIDATE_BIRTH


@dataclass
class LabeledRepo:
    repo_id: str
    category: str  # one of CATEGORIES
    split: str  # TUNING | HELDOUT
    commits: list[dict]  # {message, files, date} — materialized into a git repo
    note: str  # what this case exercises, for the artifact
    candidate: Optional[CandidateSpec] = None

    @property
    def authentic(self) -> bool:
        """Ground truth: only genuine originals are authentic."""
        return self.category == ORIGINAL


# --------------------------------------------------------------------------- #
# History builders (deterministic — no datetime.now())                         #
# --------------------------------------------------------------------------- #
_HEALTHY_MSGS = [
    "scaffold module", "implement core logic", "handle edge cases",
    "add input validation", "docstrings and cleanup", "small refactor",
    "extend test coverage", "fix off-by-one",
]
_HEALTHY_GAPS = [0, 2, 5, 9, 14, 20, 27, 33]  # irregular day gaps
_HEALTHY_TIMES = ["09:12", "22:41", "13:05", "18:53", "07:20", "23:10", "11:47", "16:38"]


def _stamp(day: date, hhmm: str) -> str:
    return f"{day.isoformat()} {hhmm}:00 +0000"


def _healthy(files: dict[str, str], n: int = 5) -> list[dict]:
    """An irregular, human-looking history that ends on the canonical sources."""
    base = date(2024, 3, 4)
    commits = []
    for i in range(n):
        # Intermediate commits carry a WIP marker so each commit is a real change;
        # the final commit holds the clean canonical content the analyzer reads.
        content = {
            p: (src if i == n - 1 else src + f"\n# wip {i}\n") for p, src in files.items()
        }
        commits.append(
            {
                "message": _HEALTHY_MSGS[i % len(_HEALTHY_MSGS)],
                "files": content,
                "date": _stamp(base + timedelta(days=_HEALTHY_GAPS[i % len(_HEALTHY_GAPS)]),
                               _HEALTHY_TIMES[i % len(_HEALTHY_TIMES)]),
            }
        )
    return commits


def _faked(files: dict[str, str], n: int = 30) -> list[dict]:
    """A fake-git-history-style run: exact 1-day gaps, fixed noon, one message."""
    base = date(2023, 11, 1)
    commits = []
    for i in range(n):
        content = {
            p: (src if i == n - 1 else src + f"\n# {i}\n") for p, src in files.items()
        }
        commits.append(
            {"message": "update", "files": content, "date": _stamp(base + timedelta(days=i), "12:00")}
        )
    return commits


def _single(files: dict[str, str]) -> list[dict]:
    return [{"message": "initial commit", "files": files, "date": _stamp(date(2024, 5, 2), "10:00")}]


# --------------------------------------------------------------------------- #
# Case constructors                                                            #
# --------------------------------------------------------------------------- #
def _cand(slug: str, files: dict[str, str]) -> CandidateSpec:
    return CandidateSpec(slug=slug, owner="upstream", files=files)


def _orig(repo_id, split, files, *, n=5, note, candidate=None) -> LabeledRepo:
    return LabeledRepo(repo_id, ORIGINAL, split, _healthy(files, n), note, candidate)


def _orig_thin(repo_id, split, files, *, note) -> LabeledRepo:
    return LabeledRepo(repo_id, ORIGINAL, split, _single(files), note)


def _copy(repo_id, split, files, cand_files, *, n=4, note) -> LabeledRepo:
    return LabeledRepo(repo_id, COPIED, split, _healthy(files, n), note,
                       _cand(f"upstream/{repo_id}-src", cand_files))


def _fake(repo_id, split, files, cand_files, *, n=30, note) -> LabeledRepo:
    return LabeledRepo(repo_id, FAKED, split, _faked(files, n), note,
                       _cand(f"upstream/{repo_id}-src", cand_files))


# --------------------------------------------------------------------------- #
# The corpus (24 labeled repos: 10 original, 8 copied, 6 faked)                #
# --------------------------------------------------------------------------- #
CORPUS: list[LabeledRepo] = [
    # -- Originals: genuine work must never be flagged -----------------------
    _orig("orig-inventory", HELDOUT, {"inventory.py": S.INVENTORY}, n=6,
          note="Standalone program, healthy history, no similar candidate."),
    _orig("orig-csv", TUNING, {"report.py": S.CSV_REPORT}, n=5,
          note="Standalone CSV summarizer, healthy history."),
    _orig("orig-lru", HELDOUT, {"cache.py": S.LRU_CACHE}, n=5,
          note="Standalone LRU cache, healthy history."),
    _orig("orig-graph", HELDOUT, {"graph.py": S.GRAPH_BFS}, n=4,
          note="Standalone BFS pathfinder, healthy history."),
    _orig("orig-ratelimit", TUNING, {"bucket.py": S.RATE_LIMITER}, n=5,
          note="Standalone rate limiter, healthy history."),
    _orig("orig-toc", HELDOUT, {"toc.py": S.MARKDOWN_TOC}, n=5,
          note="Standalone markdown TOC generator, healthy history."),
    _orig("orig-boilerplate-a", HELDOUT, {"app.py": S.FLASK_A}, n=5,
          candidate=_cand("upstream/flask-skeleton", {"app.py": S.FLASK_B}),
          note="§8.4-2: shares a Flask skeleton with an older repo — high "
               "structural, low logic. Must stay clean."),
    _orig("orig-boilerplate-b", TUNING, {"app.py": S.FLASK_B}, n=5,
          candidate=_cand("upstream/flask-skeleton", {"app.py": S.FLASK_A}),
          note="§8.4-2: boilerplate twin of orig-boilerplate-a."),
    _orig("orig-rewrite", HELDOUT, {"warehouse.py": S.WAREHOUSE}, n=5,
          candidate=_cand("upstream/inventory", {"inventory.py": S.INVENTORY}),
          note="Independent rewrite of the same domain as an older repo — low "
               "logic similarity. Must stay clean."),
    _orig_thin("orig-thin", HELDOUT, {"fib.py": S.FIB},
               note="§8.4-1: a single genuine commit → insufficient_signal, "
                    "never flagged on thin history alone."),

    # -- Copied: a fork-and-relabel or renamed clone of an older repo --------
    _copy("copy-inv-renamed", TUNING, {"ledger.py": S.INVENTORY_RENAMED},
          {"inventory.py": S.INVENTORY}, n=4,
          note="Renamed clone of an older repo (identifiers changed only)."),
    _copy("copy-inv-verbatim", HELDOUT, {"inventory.py": S.INVENTORY},
          {"inventory.py": S.INVENTORY}, n=4,
          note="Verbatim copy of an older repo."),
    _copy("copy-csv", TUNING, {"report.py": S.CSV_REPORT},
          {"report.py": S.CSV_REPORT}, n=3,
          note="Verbatim copy of an older CSV tool."),
    _copy("copy-lru", HELDOUT, {"cache.py": S.LRU_CACHE},
          {"cache.py": S.LRU_CACHE}, n=4,
          note="Verbatim copy of an older cache."),
    _copy("copy-graph", HELDOUT, {"graph.py": S.GRAPH_BFS},
          {"graph.py": S.GRAPH_BFS}, n=3,
          note="Verbatim copy of an older graph module."),
    _copy("copy-ratelimit", HELDOUT, {"bucket.py": S.RATE_LIMITER},
          {"bucket.py": S.RATE_LIMITER}, n=4,
          note="Verbatim copy of an older rate limiter."),
    _copy("copy-toc", TUNING, {"toc.py": S.MARKDOWN_TOC},
          {"toc.py": S.MARKDOWN_TOC}, n=3,
          note="Verbatim copy of an older TOC generator."),
    _copy("copy-inv-renamed-2", HELDOUT, {"stock.py": S.INVENTORY_RENAMED},
          {"inventory.py": S.INVENTORY}, n=5,
          note="Renamed clone with a longer cover history."),

    # -- Faked: copied code wrapped in a fabricated timeline (§8.4-3) --------
    _fake("fake-inv", TUNING, {"ledger.py": S.INVENTORY_RENAMED},
          {"inventory.py": S.INVENTORY}, n=30,
          note="§8.4-3: renamed clone under a fake-git-history timeline. Must "
               "still flag, driven by clone similarity, not the history."),
    _fake("fake-csv", HELDOUT, {"report.py": S.CSV_REPORT},
          {"report.py": S.CSV_REPORT}, n=30,
          note="§8.4-3: verbatim copy under a fabricated timeline."),
    _fake("fake-lru", HELDOUT, {"cache.py": S.LRU_CACHE},
          {"cache.py": S.LRU_CACHE}, n=25,
          note="§8.4-3: verbatim copy under a fabricated timeline."),
    _fake("fake-graph", TUNING, {"graph.py": S.GRAPH_BFS},
          {"graph.py": S.GRAPH_BFS}, n=40,
          note="§8.4-3: verbatim copy under a long fabricated timeline."),
    _fake("fake-ratelimit", HELDOUT, {"bucket.py": S.RATE_LIMITER},
          {"bucket.py": S.RATE_LIMITER}, n=30,
          note="§8.4-3: verbatim copy under a fabricated timeline."),
    _fake("fake-toc", HELDOUT, {"toc.py": S.MARKDOWN_TOC},
          {"toc.py": S.MARKDOWN_TOC}, n=28,
          note="§8.4-3: verbatim copy under a fabricated timeline."),
]


# --------------------------------------------------------------------------- #
# Split accessors + the disjointness invariant (spec §8.4-6)                   #
# --------------------------------------------------------------------------- #
def all_repos() -> list[LabeledRepo]:
    return list(CORPUS)


def for_split(split: str) -> list[LabeledRepo]:
    if split == "all":
        return all_repos()
    if split not in (TUNING, HELDOUT):
        raise ValueError(f"unknown split {split!r}; expected tuning|heldout|all")
    return [r for r in CORPUS if r.split == split]


def tuning_set() -> list[LabeledRepo]:
    return for_split(TUNING)


def heldout_set() -> list[LabeledRepo]:
    return for_split(HELDOUT)


def split_ids() -> dict[str, set[str]]:
    return {
        TUNING: {r.repo_id for r in tuning_set()},
        HELDOUT: {r.repo_id for r in heldout_set()},
    }


def assert_no_leakage() -> None:
    """The tuning and held-out sets must be disjoint and cover every category.

    This is the structural half of the §8.4-6 evaluation-leakage guard: reported
    metrics can only be untainted if the split they come from never overlaps the
    set used for tuning. Raises AssertionError if the invariant is broken.
    """
    ids = [r.repo_id for r in CORPUS]
    assert len(ids) == len(set(ids)), "duplicate repo_id in the corpus"

    tuning, heldout = split_ids()[TUNING], split_ids()[HELDOUT]
    assert tuning and heldout, "both splits must be non-empty"
    assert tuning.isdisjoint(heldout), f"split leakage: {tuning & heldout}"

    for split_repos, name in ((tuning_set(), TUNING), (heldout_set(), HELDOUT)):
        present = {r.category for r in split_repos}
        assert present == set(CATEGORIES), f"{name} split missing categories: {set(CATEGORIES) - present}"
