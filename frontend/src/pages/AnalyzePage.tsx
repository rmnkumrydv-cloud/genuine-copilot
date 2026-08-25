import { useEffect, useState } from "react";
import type { AnalysisPayload, Health, Rules } from "../api/client";
import { analyzeRepo, errorMessage, getHealth, getRules } from "../api/client";
import ReportView from "../components/ReportView";
import { Spinner } from "../components/ui";

const STAGES = [
  "Cloning & ranking significant files",
  "Fingerprinting & clone detection",
  "Verifying README claims (RAG grounding)",
  "Commit forensics",
  "Scoring & four-branch verdict",
];

export default function AnalyzePage() {
  const [repoUrl, setRepoUrl] = useState("");
  const [explain, setExplain] = useState(false);
  const [loading, setLoading] = useState(false);
  const [stage, setStage] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const [payload, setPayload] = useState<AnalysisPayload | null>(null);
  const [rules, setRules] = useState<Rules | null>(null);
  const [health, setHealth] = useState<Health | null>(null);

  useEffect(() => {
    getRules().then(setRules).catch(() => setRules(null));
    getHealth().then(setHealth).catch(() => setHealth(null));
  }, []);

  useEffect(() => {
    if (!loading) return;
    setStage(0);
    const id = setInterval(() => setStage((s) => (s + 1) % STAGES.length), 900);
    return () => clearInterval(id);
  }, [loading]);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    const url = repoUrl.trim();
    if (!url || loading) return;
    setLoading(true);
    setError(null);
    setPayload(null);
    try {
      setPayload(await analyzeRepo(url, explain));
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setLoading(false);
    }
  }

  const llmOff = health && !health.llm_configured;

  return (
    <div className="flex flex-col gap-6">
      <section className="card">
        <h1 className="text-lg font-semibold text-slate-100">
          Analyze a repository
        </h1>
        <p className="mt-1 text-sm text-slate-400">
          Paste a public GitHub URL or a local path. The verdict is computed by a
          deterministic, auditable core — an LLM never decides authenticity.
        </p>

        <form onSubmit={submit} className="mt-4 flex flex-col gap-3 sm:flex-row">
          <input
            className="input flex-1"
            placeholder="https://github.com/owner/repo  ·  or  ./path/to/repo"
            value={repoUrl}
            onChange={(e) => setRepoUrl(e.target.value)}
            disabled={loading}
            spellCheck={false}
          />
          <button type="submit" className="btn-primary sm:w-40" disabled={loading}>
            {loading ? "Analyzing…" : "Analyze"}
          </button>
        </form>

        <div className="mt-3 flex flex-wrap items-center gap-2 text-sm">
          <label className="flex cursor-pointer items-center gap-2 text-slate-300">
            <input
              type="checkbox"
              className="h-4 w-4 rounded border-slate-600 bg-slate-900 accent-sky-500"
              checked={explain}
              onChange={(e) => setExplain(e.target.checked)}
              disabled={loading}
            />
            Add AI explanation &amp; interview questions
          </label>
          {llmOff && explain && (
            <span className="text-xs text-amber-400/90">
              no Groq key detected — will fall back to the deterministic template
            </span>
          )}
        </div>
      </section>

      {loading && (
        <section className="card">
          <Spinner label="Running the deterministic pipeline…" />
          <ol className="mt-4 space-y-2">
            {STAGES.map((s, i) => (
              <li
                key={s}
                className={`flex items-center gap-3 text-sm ${
                  i === stage ? "text-sky-300" : "text-slate-500"
                }`}
              >
                <span
                  className={`h-1.5 w-1.5 rounded-full ${
                    i <= stage ? "bg-sky-400" : "bg-slate-700"
                  }`}
                />
                {s}
              </li>
            ))}
          </ol>
        </section>
      )}

      {error && (
        <section className="card border-red-500/40 bg-red-500/5">
          <div className="text-sm font-semibold text-red-300">Analysis failed</div>
          <p className="mt-1 text-sm text-slate-300">{error}</p>
        </section>
      )}

      {payload && !loading && <ReportView payload={payload} rules={rules} />}
    </div>
  );
}
