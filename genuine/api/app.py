"""FastAPI server (spec §4 backend).

Exposes the analysis pipeline as JSON. For the deterministic-core milestone the
analysis runs synchronously and is persisted to the ``jobs`` table; an async job
queue with live progress is a straightforward later enhancement (the row model
already supports queued/running/done/error states).

Endpoints:
  GET  /health            liveness + whether GitHub/LLM creds are present
  GET  /rules             the rulebook (auditability — the frontend renders it)
  POST /analyze           run analysis on {repo_url}; returns the full payload
  GET  /jobs/{job_id}     fetch a stored analysis result
"""

from __future__ import annotations

import json
import uuid

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from ..config import get_settings
from ..pipeline import analyze
from ..scoring import Rulebook
from ..store import connect, init_schema
from ..ingestion.github import utcnow

app = FastAPI(title="Genuine API", version="0.1.0")

# The dashboard (Vite dev server / Vercel) calls this cross-origin.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


class AnalyzeRequest(BaseModel):
    repo_url: str
    explain: bool = False  # opt-in Groq explanation + interview probes (advisory)


@app.get("/health")
def health() -> dict:
    s = get_settings()
    return {
        "status": "ok",
        "github_auth": s.has_github_auth,
        "llm_configured": s.has_llm,
    }


@app.get("/rules")
def rules() -> dict:
    rb = Rulebook.load()
    return {
        "weights": rb.weights,
        "thresholds": {"flagged": rb.flagged, "review_low": rb.review_low},
        "insufficient_signal": {"min_commits": rb.min_commits, "min_coverage": rb.min_coverage},
        "note": "Sub-scores are suspicion values in [0,1]; higher = more likely inauthentic.",
    }


@app.post("/analyze")
def analyze_repo(req: AnalyzeRequest) -> dict:
    s = get_settings()
    init_schema(s.db_file)
    job_id = uuid.uuid4().hex
    now = utcnow().isoformat()

    with connect(s.db_file) as conn:
        conn.execute(
            "INSERT INTO jobs (id, repo_url, status, created_at, updated_at) VALUES (?,?,?,?,?)",
            (job_id, req.repo_url, "running", now, now),
        )

    try:
        result = analyze(
            req.repo_url,
            db_path=s.db_file,
            cache_root=s.clone_dir,
            token=s.github_token,
            explain=req.explain,
        )
        payload = result.to_payload()
        payload["job_id"] = job_id
        with connect(s.db_file) as conn:
            conn.execute(
                "UPDATE jobs SET status=?, updated_at=?, result_json=? WHERE id=?",
                ("done", utcnow().isoformat(), json.dumps(payload, default=str), job_id),
            )
        return payload
    except Exception as exc:  # surface the failure honestly instead of a 500 blob
        with connect(s.db_file) as conn:
            conn.execute(
                "UPDATE jobs SET status=?, updated_at=?, error=? WHERE id=?",
                ("error", utcnow().isoformat(), str(exc), job_id),
            )
        raise HTTPException(status_code=400, detail=f"Analysis failed: {exc}") from exc


@app.get("/jobs/{job_id}")
def get_job(job_id: str) -> dict:
    s = get_settings()
    init_schema(s.db_file)
    with connect(s.db_file) as conn:
        row = conn.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="job not found")
    out = {"job_id": row["id"], "repo_url": row["repo_url"], "status": row["status"]}
    if row["result_json"]:
        out["result"] = json.loads(row["result_json"])
    if row["error"]:
        out["error"] = row["error"]
    return out
