import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import type { JobSummary, Verdict } from "../api/client";
import { errorMessage, listJobs } from "../api/client";
import VerdictBadge from "../components/VerdictBadge";
import { EmptyState, Spinner } from "../components/ui";
import { formatDateTime, shortRepo } from "../lib/format";

type Filter = "needs_human_review" | "flagged" | "clean" | "all";

const FILTERS: { key: Filter; label: string }[] = [
  { key: "needs_human_review", label: "Needs review" },
  { key: "flagged", label: "Flagged" },
  { key: "clean", label: "Clean" },
  { key: "all", label: "All" },
];

export default function QueuePage() {
  const [jobs, setJobs] = useState<JobSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [filter, setFilter] = useState<Filter>("needs_human_review");

  async function load() {
    setLoading(true);
    setError(null);
    try {
      setJobs(await listJobs());
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    load();
  }, []);

  const counts = useMemo(() => {
    const c: Record<string, number> = {};
    for (const j of jobs) if (j.verdict) c[j.verdict] = (c[j.verdict] ?? 0) + 1;
    return c;
  }, [jobs]);

  const shown =
    filter === "all" ? jobs : jobs.filter((j) => j.verdict === filter);

  return (
    <div className="flex flex-col gap-5">
      <section className="card">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <h1 className="text-lg font-semibold text-slate-100">Review queue</h1>
            <p className="mt-1 text-sm text-slate-400">
              Borderline cases awaiting human judgment, evidence pre-assembled.
              Clean and flagged cases resolve automatically — a person only needs
              the <span className="text-amber-300">needs-review</span> slice.
            </p>
          </div>
          <button onClick={load} className="btn-ghost" disabled={loading}>
            Refresh
          </button>
        </div>

        <div className="mt-4 flex flex-wrap gap-2">
          {FILTERS.map((f) => {
            const n = f.key === "all" ? jobs.length : counts[f.key] ?? 0;
            return (
              <button
                key={f.key}
                onClick={() => setFilter(f.key)}
                className={`chip ${
                  filter === f.key
                    ? "border-sky-400/50 bg-sky-500/10 text-sky-200"
                    : "border-slate-700 text-slate-400 hover:text-slate-200"
                }`}
              >
                {f.label} · {n}
              </button>
            );
          })}
        </div>
      </section>

      {loading ? (
        <div className="card">
          <Spinner label="Loading recent analyses…" />
        </div>
      ) : error ? (
        <section className="card border-red-500/40 bg-red-500/5">
          <p className="text-sm text-red-300">{error}</p>
        </section>
      ) : shown.length === 0 ? (
        <EmptyState title="Nothing here">
          {filter === "needs_human_review"
            ? "No borderline cases in the queue — everything analyzed so far resolved automatically."
            : "No analyses match this filter yet."}
        </EmptyState>
      ) : (
        <div className="flex flex-col gap-2">
          {shown.map((j) => (
            <Link
              key={j.job_id}
              to={`/jobs/${j.job_id}`}
              className="card-tight flex items-center justify-between gap-4 transition-colors hover:border-slate-600 hover:bg-slate-900"
            >
              <div className="min-w-0">
                <div className="truncate text-sm font-medium text-slate-100">
                  {shortRepo({ repo_url: j.repo_url, repo_name: j.repo_name })}
                </div>
                <div className="truncate text-xs text-slate-500">
                  {formatDateTime(j.created_at)}
                </div>
              </div>
              <div className="flex items-center gap-4">
                {j.composite_score != null && (
                  <span className="tabular-nums text-sm text-slate-400">
                    {j.composite_score.toFixed(2)}
                  </span>
                )}
                {j.verdict ? (
                  <VerdictBadge verdict={j.verdict as Verdict} size="sm" />
                ) : (
                  <span className="chip border-slate-700 text-slate-400">
                    {j.status}
                  </span>
                )}
              </div>
            </Link>
          ))}
        </div>
      )}
    </div>
  );
}
