import { useEffect, useState } from "react";
import { NavLink, Navigate, Route, Routes } from "react-router-dom";
import type { Health } from "./api/client";
import { getHealth } from "./api/client";
import AnalyzePage from "./pages/AnalyzePage";
import JobDetailPage from "./pages/JobDetailPage";
import QueuePage from "./pages/QueuePage";

function HealthDot({ health, failed }: { health: Health | null; failed: boolean }) {
  const color = failed
    ? "bg-red-400"
    : health
      ? "bg-emerald-400"
      : "bg-slate-500";
  const title = failed
    ? "API unreachable"
    : health
      ? `API ok · Groq ${health.llm_configured ? "configured" : "off"} · GitHub ${
          health.github_auth ? "authed" : "anon"
        }`
      : "checking…";
  return (
    <span className="flex items-center gap-2 text-xs text-slate-400" title={title}>
      <span className={`h-2 w-2 rounded-full ${color}`} />
      <span className="hidden sm:inline">
        {failed ? "API offline" : health ? "API ok" : "…"}
      </span>
    </span>
  );
}

const navClass = ({ isActive }: { isActive: boolean }) =>
  `rounded-lg px-3 py-1.5 text-sm font-medium transition-colors ${
    isActive ? "bg-slate-800 text-slate-100" : "text-slate-400 hover:text-slate-200"
  }`;

export default function App() {
  const [health, setHealth] = useState<Health | null>(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    getHealth().then(setHealth).catch(() => setFailed(true));
  }, []);

  return (
    <div className="min-h-full">
      <header className="sticky top-0 z-10 border-b border-slate-800 bg-slate-950/80 backdrop-blur">
        <div className="mx-auto flex max-w-5xl items-center justify-between px-4 py-3">
          <div className="flex items-center gap-6">
            <NavLink to="/" className="flex items-center gap-2">
              <span className="text-lg font-bold tracking-tight text-slate-100">
                Genuine
              </span>
              <span className="hidden text-xs text-slate-500 sm:inline">
                authenticity review
              </span>
            </NavLink>
            <nav className="flex items-center gap-1">
              <NavLink to="/" end className={navClass}>
                Analyze
              </NavLink>
              <NavLink to="/queue" className={navClass}>
                Review queue
              </NavLink>
            </nav>
          </div>
          <HealthDot health={health} failed={failed} />
        </div>
      </header>

      <main className="mx-auto max-w-5xl px-4 py-8">
        <Routes>
          <Route path="/" element={<AnalyzePage />} />
          <Route path="/queue" element={<QueuePage />} />
          <Route path="/jobs/:id" element={<JobDetailPage />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </main>

      <footer className="mx-auto max-w-5xl px-4 pb-10 text-center text-xs text-slate-600">
        Every verdict is deterministic, auditable, and reproducible. The LLM
        layer is advisory only and can never change a score.
      </footer>
    </div>
  );
}
