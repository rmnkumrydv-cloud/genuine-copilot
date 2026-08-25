import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import type { JobDetail, Rules } from "../api/client";
import { errorMessage, getJob, getRules } from "../api/client";
import ReportView from "../components/ReportView";
import { EmptyState, Spinner } from "../components/ui";

export default function JobDetailPage() {
  const { id = "" } = useParams();
  const [job, setJob] = useState<JobDetail | null>(null);
  const [rules, setRules] = useState<Rules | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setLoading(true);
    setError(null);
    getRules()
      .then(setRules)
      .catch(() => setRules(null));
    getJob(id)
      .then(setJob)
      .catch((err) => setError(errorMessage(err)))
      .finally(() => setLoading(false));
  }, [id]);

  return (
    <div className="flex flex-col gap-5">
      <Link to="/queue" className="text-sm text-sky-400 hover:text-sky-300">
        ← Back to review queue
      </Link>

      {loading ? (
        <div className="card">
          <Spinner label="Loading analysis…" />
        </div>
      ) : error ? (
        <section className="card border-red-500/40 bg-red-500/5">
          <p className="text-sm text-red-300">{error}</p>
        </section>
      ) : job?.result ? (
        <ReportView payload={job.result} rules={rules} />
      ) : (
        <EmptyState title="No result stored">
          {job?.error
            ? `This job ended in an error: ${job.error}`
            : `Job ${id} has status “${job?.status ?? "unknown"}” and no stored result.`}
        </EmptyState>
      )}
    </div>
  );
}
