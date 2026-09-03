# Genuine

**A neuro-symbolic project-authenticity & interview-prep copilot.**

[![Live Demo](https://img.shields.io/badge/Live%20Demo-genuine--copilot2.vercel.app-blue?style=for-the-badge)](https://genuine-copilot2.vercel.app)
[![GitHub](https://img.shields.io/badge/GitHub-genuine--copilot-181717?style=for-the-badge&logo=github)](https://github.com/rmnkumrydv-cloud/genuine-copilot)

![Python](https://img.shields.io/badge/Python-3.11+-3776AB?logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-0.110+-009688?logo=fastapi&logoColor=white)
![React](https://img.shields.io/badge/React-18-61DAFB?logo=react&logoColor=black)
![TypeScript](https://img.shields.io/badge/TypeScript-5.6-3178C6?logo=typescript&logoColor=white)
![Tailwind CSS](https://img.shields.io/badge/Tailwind-3.4-06B6D4?logo=tailwindcss&logoColor=white)
![Tests](https://img.shields.io/badge/Tests-105%20passed-brightgreen)

Genuine scores how likely a GitHub repository is to be *genuinely the author's
own work* — copied code, resubmitted projects, fabricated commit history, and
READMEs that lie about the stack. It is built on one hard rule:

> **Every originality judgment is deterministic, auditable, and reproducible.
> An LLM never decides whether something is authentic.**

The LLM appears only at the very end, as an *explainer* (Gate 5) — even the
README claim-extraction and code-region retrieval of Gate 4 are deterministic.
The verdict itself comes from code you can read, re-run, and argue with — which is
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

When the Groq explainer runs (Gate 5, `genuine/llm/`), it receives the finished
score and evidence *summaries* and writes prose *about* them plus interview
questions. It cannot change a number, and it never sees raw source or README
text — so a hostile repo has no channel to inject instructions (see
[AI explanation & interview prep](#ai-explanation--interview-prep-gate-5)).

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

## README grounding & code retrieval (Gate 4)

The `readme_consistency` signal answers *"does the README lie about the stack?"*
Gate 4 (`genuine/rag/`) adds a second, **advisory** layer on top: it locates the
code region behind each claim and attaches a `file:line` citation, so a reviewer
sees not just *that* a claim checks out but *where*.

It is deterministic RAG — **no embeddings, no network.** The corpus is a single
repo's significant files, so a classic identifier-aware **TF-IDF cosine**
retriever (`rag/retrieval.py`) is both sufficient and fully auditable — you can
hand-check any score. Files are chunked by structure: each top-level `def`/`class`
and the module preamble become their own retrievable region (`rag/chunking.py`),
falling back to line windows for non-Python or unparseable files. Tokenization is
identifier-aware, so the query `export csv` matches `def export_csv` and `fastapi`
matches `from fastapi import FastAPI`.

- **Tech-stack claims** (the scoring authority) stay deterministic and now carry a
  citation to the importing file or manifest when verified. The checked
  vocabulary spans web frameworks, data stores (Redis, Postgres, MongoDB),
  scientific/ML stacks, and the JS/TS frontend — each gated on its ecosystem so a
  claim is only ever *contradicted* when that ecosystem is plainly present.
- **Feature / setup claims** (`rag/claims.py`) are extracted heuristically and
  *grounded*: retrieval finds the implementing code → `VERIFIED` + citation, or a
  miss → `UNVERIFIED`. A miss is **never** a contradiction, so grounding cannot
  raise a false flag (`test_ungrounded_feature_is_unverified_not_contradicted`).

The split is the point: grounding enriches the evidence a human reads but **never
moves the suspicion score** — the deterministic contradiction path is byte-for-byte
unchanged. And retrieval feeds the deterministic verifier, *not* the LLM, so Gate
5's no-raw-code boundary stays intact: the model still sees only citations and
summaries, never the retrieved source.

---

## AI explanation & interview prep (Gate 5)

The deterministic verdict is the product. The LLM is a **reader's aide** bolted on
top — opt-in, and structurally incapable of changing the result.

`genuine/llm/` makes **one** Groq call (LLaMA-3.3-70B, JSON mode) that returns
two things for the human reviewer:

- an **explanation** — plain-language prose about what the verdict and evidence
  mean, and what to check in person;
- **interview questions** — tied to the evidence, so an honest author can
  demonstrate they actually wrote and understand the code (e.g. *"walk me through
  your diff algorithm"* when a clone signal fired).

Two properties are enforced, not promised:

1. **The verdict is immutable.** The explainer's output attaches to the API
   payload (`ai_opinion`, `interview_probes`), never to the `ScoreResult` the
   aggregator produces. `test_explanation_never_changes_the_verdict` runs the
   pipeline with the LLM on and off and asserts the composite is identical.
2. **The model never sees raw code.** Its entire input is the verdict, the
   sub-scores, and the human-safe evidence *summaries* — assembled by a function
   whose signature *cannot* accept source or README text
   (`test_input_boundary_has_no_raw_source_parameter`). That closes prompt
   injection: a repo can't smuggle *"ignore previous instructions"* into the
   prompt via a comment, because its comments are never in the prompt.

No `GROQ_API_KEY`? Every path degrades to `None`/`[]` and the deterministic
template report (`genuine/report.py`) stands alone. All Gate-5 tests run fully
offline (mocked client); a guard fails the suite if any test attempts a live call.

---

## Reviewer dashboard (Gate 6)

`frontend/` is a React + Vite + TypeScript + Tailwind app that **renders** the
deterministic verdict — it never computes one. It consumes only the API payload
(verdict, sub-scores, evidence summaries, README claims, commit metadata, and the
optional advisory note); it never receives repo source, consistent with the
privacy stance above.

- **Analyze** — submit a URL or local path, watch the pipeline run, read the report.
- **Report** — the composite suspicion meter (with the review/flag thresholds
  drawn in) and the four sub-score bars showing `weight × score → contribution`.
- **Evidence** — a Recharts commit-cadence timeline (from the new
  `commit_timeline` payload field), evidence cards grouped by signal, and the
  README claim table with its RAG `file:line` citations.
- **Interview prep** — the evidence-tied questions, each linking back to the exact
  evidence card it probes.
- **Review queue** — borderline `needs_human_review` cases first (via
  `GET /jobs?status=…`). The advisory AI opinion is rendered in a visually
  separated, dashed "advisory only" card so it can never be mistaken for symbolic
  evidence — the neuro-symbolic boundary, made visible.

```bash
uvicorn genuine.api:app --reload      # terminal 1: the deterministic core at :8000
cd frontend && npm install && npm run dev   # terminal 2: the dashboard at :5173
```

Dev proxies `/api/*` → `127.0.0.1:8000` (no CORS/base-URL config). See
`frontend/README.md`.

---

## Getting started

Requires Python ≥ 3.11 (developed on 3.13).

```bash
python -m venv .venv
source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements.txt
pip install -e .

pytest                              # 105 tests
```

### CLI

```bash
# Analyze a local repo or a GitHub URL (no network needed for local paths)
genuine analyze ./some/repo

# Compare against a known original to exercise clone detection offline
genuine analyze ./tests/fixtures/renamed --candidate ./tests/fixtures/original

genuine analyze ./some/repo --json      # full machine-readable payload

# Add a Groq LLM explanation + interview questions (advisory; needs GROQ_API_KEY).
# Without a key it prints a one-line notice and the deterministic report stands.
genuine analyze ./some/repo --explain
```

### API

```bash
uvicorn genuine.api:app --reload
```

| Method | Path | Purpose |
|---|---|---|
| `GET`  | `/health`      | Liveness |
| `GET`  | `/rules`       | The active weights & thresholds (auditability) |
| `POST` | `/analyze`     | `{"repo_url": "<url or local path>", "explain": false}` → verdict + evidence + `commit_timeline` + `job_id` (set `explain: true` to add the advisory `ai_opinion` + `interview_probes`) |
| `GET`  | `/jobs`        | Recent analyses (summaries); `?status=needs_human_review` powers the review queue |
| `GET`  | `/jobs/{id}`   | Fetch a persisted analysis |

### Docker

```bash
docker compose up --build
# API at :8000, Dashboard at :8080
```

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
  rag/              # Gate 4: deterministic TF-IDF retrieval + README claim grounding
  scoring/          # rules.yaml (the auditable artifact) + aggregator
  llm/              # Gate 5: advisory Groq explainer + interview probes (opt-in)
  eval/             # labeled evaluation corpus + harness + metrics
  api/              # FastAPI app
  pipeline.py       # end-to-end: ingest → signals → score → report → registry
  report.py         # zero-LLM template report (the neuro-symbolic fallback)
  cli.py            # `genuine analyze`
frontend/           # React/Vite/Tailwind reviewer dashboard (renders, never scores)
tests/              # 105 tests incl. every spec §8.4 regression case
```

---

## License

MIT.
