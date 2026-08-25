# Genuine

**A neuro-symbolic project-authenticity & interview-prep copilot.**
Razorpay AI Buildathon 2026.

Genuine scores how likely a GitHub repository is to be *genuinely the author's
own work* — copied code, resubmitted projects, fabricated commit history, and
READMEs that lie about the stack. It is built on one hard rule:

> **Every originality judgment is deterministic, auditable, and reproducible.
> An LLM never decides whether something is authentic.**

AI is used only for *extraction, retrieval, and explanation* (later gates). The
verdict itself comes from code you can read, re-run, and argue with — which is
the only kind of verdict a hiring-integrity tool has any business producing.

---

## The neuro-symbolic boundary (why this design)

A model that says "this looks copied" is unfalsifiable and ungameable-in-the-
wrong-direction: you can't appeal it, and it can't show its work. So the scoring
core has **no channel through which an LLM opinion could reach a verdict** — this
is enforced structurally, not by good intentions:

- `genuine/scoring/aggregator.py` — `aggregate(...)` has no `ai_opinion`
  parameter, and a test (`test_aggregate_signature_has_no_ai_opinion_param`)
  fails if anyone adds one.
- The scoring rulebook is **data**, not code (`genuine/scoring/rules.yaml`).
  Changing a weight changes the verdict with zero code change — proven by
  `test_weights_are_data_not_code`.

When the Groq explainer lands (Gate 5), it will receive the finished score and
evidence and write prose *about* them. It cannot change a number.

---

## How the score works

**Direction convention:** every sub-score is a **suspicion** value in `[0, 1]`
— *higher means more likely inauthentic*. The composite is a plain weighted sum
(weights sum to 1.0):

```
composite = Σ weightᵢ · sub_scoreᵢ
```

### The four deterministic signals

| Signal | Weight | What it measures | Module |
|---|---|---|---|
| `clone_similarity`   | 0.45 | Copied code vs. candidate repos, via AST + normalized-token similarity | `signals/clone.py`, `signals/similarity.py` |
| `registry_match`     | 0.20 | Near-duplicate of another submission (MinHash over the shared registry) | `signals/registry.py` |
| `readme_consistency` | 0.20 | README tech-stack claims contradicted by the actual code | `signals/readme_consistency.py` |
| `commit_forensics`   | 0.15 | Fabricated / dumped commit history (regular intervals, fixed time-of-day, canned messages, timestamp collisions) | `signals/commit_forensics.py` |

**Two axes of code similarity, reported separately** (`similarity.py`):

- **structural** — order-insensitive shape of the AST (construct vocabulary +
  local arrangement). Shared framework boilerplate scores *high* here.
- **logic** — the normalized token stream (identifiers → `NAME`, literals →
  `LIT`, keywords/operators kept), blended with the **longest contiguous
  matching run**. This is what catches a copy that survives renaming, while a
  plain diff-ratio would be fooled by scattered shared glue.

Only **logic** drives the clone score. That is precisely what lets two
independent Flask apps (*high structural, low logic*) come back **clean** while a
renamed copy (*high on both*) gets flagged — spec regression case §8.4-2.

### Four-branch verdict

```
critical signal tripped (e.g. clone ≥ 0.85)   -> flagged        (decisive alone)
composite ≥ 0.65                               -> flagged
0.45 ≤ composite < 0.65                        -> needs_human_review
composite < 0.45, thin history/coverage        -> insufficient_signal
otherwise                                      -> clean
```

The **critical-signal override** exists because clone similarity is weighted
0.45, so a verbatim copy with no other signal tops out at composite 0.45
(`needs_human_review`) on its own. A blatant copy must flag *by itself* (spec
§8.4-3), so a single signal above its critical cutoff is decisive — applied to
the **direction-weighted** score, so a candidate that postdates the target can
never trip it.

### Leakage guards (spec §8.4)

- **Self-match exclusion** — a repo is never compared against itself or another
  repo from the same owner.
- **Temporal direction** — a match only raises suspicion of *the target* copying
  when the candidate provably predates it; a newer candidate is heavily
  down-weighted (it may have copied *us*).
- **Structure-vs-logic split** — shared boilerplate cannot inflate the score.

---

## Quickstart

Requires Python ≥ 3.11 (developed on 3.13).

```bash
python -m venv .venv
source .venv/Scripts/activate      # Windows (Git Bash);  .venv/bin/activate on macOS/Linux
pip install -r requirements.txt
pip install -e .

pytest                              # 54 tests, ~90% coverage on the core
```

### CLI

```bash
# Analyze a local repo or a GitHub URL (no network needed for local paths)
genuine analyze ./some/repo

# Compare against a known original to exercise clone detection offline
genuine analyze ./tests/fixtures/renamed --candidate ./tests/fixtures/original

genuine analyze ./some/repo --json      # full machine-readable payload
```

### API

```bash
uvicorn genuine.api:app --reload
```

| Method | Path | Purpose |
|---|---|---|
| `GET`  | `/health`      | Liveness |
| `GET`  | `/rules`       | The active weights & thresholds (auditability) |
| `POST` | `/analyze`     | `{"repo_url": "<url or local path>"}` → verdict + evidence + `job_id` |
| `GET`  | `/jobs/{id}`   | Fetch a persisted analysis |

---

## Configuration

The deterministic core needs **no** configuration. Copy `.env.example` to `.env`
only to unlock network paths:

- `GITHUB_TOKEN` — optional; raises the GitHub API rate limit (60 → 5000 req/hr).
- `GROQ_API_KEY` / `GROQ_MODEL` — the LLM explainer (Gate 5). Absent → the
  deterministic **template report** is used instead (see `genuine/report.py`).
- `GENUINE_DB_PATH` / `GENUINE_CLONE_CACHE` — storage (defaults under `data/`,
  which is git-ignored).

### Privacy note

The deterministic core runs **entirely offline** and sends nothing anywhere.
Cloning/analysis happens locally; the only network calls are the optional GitHub
fetch (public metadata) and, if you enable it, the Groq explainer — which
receives the *already-computed* score and evidence, never raw private code, and
never influences the verdict. The shared registry stores only a MinHash
**fingerprint** (a set of integers), not source.

---

## Project layout

```
genuine/
  ingestion/        # clone/fetch, language detection, significance ranking, MinHash
  signals/          # the four deterministic signals + swappable clone matcher
  scoring/          # rules.yaml (the auditable artifact) + aggregator
  api/              # FastAPI app
  pipeline.py       # end-to-end: ingest → signals → score → report → registry
  report.py         # zero-LLM template report (the neuro-symbolic fallback)
  cli.py            # `genuine analyze`
tests/              # 54 tests incl. every spec §8.4 regression case
```

---

## Status

**Built now — the deterministic core (Gates 0–3):** ingestion, all four signals,
`rules.yaml`-driven scoring with the four-branch verdict + critical override, the
shared registry, the CLI, and the FastAPI surface. Fully tested, offline.

**Deferred to follow-up passes (per the spec):**

- Gate 4 — RAG-backed README claim *extraction* + code-region retrieval.
- Gate 5 — Groq LLaMA-3.3-70B explainer over the finished verdict (template
  fallback already ships).
- Gate 6 — React/Vite/Tailwind reviewer dashboard.
- Gate 7 — evaluation dataset + leakage-audit harness.

The similarity matcher is intentionally swappable (`signals/matchers.py`):
`copydetect`/JPlag can be slotted in behind the same interface for the Gate-2
benchmark without touching the scorer.

---

## License

MIT.
