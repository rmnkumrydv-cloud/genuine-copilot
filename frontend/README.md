# Genuine — Reviewer Dashboard (Gate 6)

React + Vite + TypeScript + Tailwind + Recharts front-end for the Genuine
authenticity engine. It renders the deterministic verdict — it never computes one.

## Pages

- **Analyze** (`/`) — submit a GitHub URL or local path; watch the pipeline run;
  read the report. Optional "Add AI explanation" toggles the advisory Groq layer.
- **Report tab** — composite suspicion meter with the review/flag thresholds,
  the four sub-score bars (weight × score → contribution), and the advisory AI
  opinion rendered in a visually separated, dashed "advisory only" card.
- **Evidence tab** — commit-cadence timeline (Recharts), evidence cards grouped
  by signal (clone / registry / README / commit), and the README claim table
  (verified / contradicted / unverified with RAG citations).
- **Interview prep tab** — evidence-tied questions; each links back to the exact
  evidence card it probes.
- **Review queue** (`/queue`) — borderline `needs_human_review` cases first, with
  evidence pre-assembled; click through to the full report (`/jobs/:id`).

## Running it

The dashboard talks to the Genuine API. Start the backend first:

```bash
# from the repo root
uvicorn genuine.api:app --reload      # serves http://127.0.0.1:8000
```

Then the dashboard:

```bash
cd frontend
npm install
npm run dev                           # http://localhost:5173
```

In dev, Vite proxies `/api/*` → `http://127.0.0.1:8000` (see `vite.config.ts`),
so no CORS or base-URL config is needed. For a deployed backend, set
`VITE_API_BASE` (copy `.env.example` → `.env`).

## Scripts

| Command | What it does |
|---|---|
| `npm run dev` | Vite dev server with API proxy |
| `npm run build` | Production build to `dist/` |
| `npm run typecheck` | `tsc --noEmit` |
| `npm run preview` | Serve the production build locally |

## Design boundary

The client only ever consumes the API payload: verdict, sub-scores, evidence
summaries, README claims, commit metadata, and (if enabled) the advisory AI note.
It never receives repo source — consistent with the engine's privacy stance.
