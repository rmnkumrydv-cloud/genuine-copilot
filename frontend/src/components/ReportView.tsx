import { useEffect, useState } from "react";
import type { AnalysisPayload, Rules } from "../api/client";
import { shortRepo } from "../lib/format";
import AiOpinion from "./AiOpinion";
import CommitTimeline from "./CommitTimeline";
import EvidenceList from "./EvidenceList";
import InterviewProbes from "./InterviewProbes";
import ReadmeClaims from "./ReadmeClaims";
import RulesPanel from "./RulesPanel";
import ScoreOverview from "./ScoreOverview";
import SubScoreBars from "./SubScoreBars";
import VerdictBadge from "./VerdictBadge";

type Tab = "report" | "evidence" | "interview";

export default function ReportView({
  payload,
  rules,
}: {
  payload: AnalysisPayload;
  rules: Rules | null;
}) {
  const [tab, setTab] = useState<Tab>("report");
  const [highlightId, setHighlightId] = useState<string | null>(null);
  const isUrl = /^https?:\/\//i.test(payload.repo_url);

  useEffect(() => {
    if (tab === "evidence" && highlightId) {
      const el = document.getElementById(`evidence-${highlightId}`);
      el?.scrollIntoView({ behavior: "smooth", block: "center" });
    }
  }, [tab, highlightId]);

  const jump = (id: string) => {
    setHighlightId(id);
    setTab("evidence");
  };

  const tabs: { key: Tab; label: string }[] = [
    { key: "report", label: "Report" },
    { key: "evidence", label: `Evidence · ${payload.evidence.length}` },
    { key: "interview", label: `Interview prep · ${payload.interview_probes.length}` },
  ];

  return (
    <div className="flex flex-col gap-5">
      <header className="flex flex-wrap items-start justify-between gap-4">
        <div className="min-w-0">
          <h2 className="truncate text-xl font-semibold text-slate-100">
            {shortRepo(payload)}
          </h2>
          {isUrl ? (
            <a
              href={payload.repo_url}
              target="_blank"
              rel="noreferrer"
              className="text-sm text-sky-400 hover:text-sky-300"
            >
              {payload.repo_url} ↗
            </a>
          ) : (
            <code className="text-sm text-slate-500">{payload.repo_url}</code>
          )}
        </div>
        <VerdictBadge verdict={payload.verdict} size="lg" />
      </header>

      <RulesPanel rules={rules} />

      <nav className="flex gap-1 border-b border-slate-800">
        {tabs.map((t) => (
          <button
            key={t.key}
            onClick={() => setTab(t.key)}
            className={`-mb-px border-b-2 px-4 py-2 text-sm font-medium transition-colors ${
              tab === t.key
                ? "border-sky-400 text-sky-300"
                : "border-transparent text-slate-400 hover:text-slate-200"
            }`}
          >
            {t.label}
          </button>
        ))}
      </nav>

      {tab === "report" && (
        <div className="flex flex-col gap-5">
          <ScoreOverview payload={payload} rules={rules} />
          <SubScoreBars payload={payload} rules={rules} />
          {payload.ai_opinion && <AiOpinion opinion={payload.ai_opinion} />}
          {payload.report_text && (
            <details className="card">
              <summary className="cursor-pointer text-sm font-semibold text-slate-200">
                Plain-text report (deterministic template)
              </summary>
              <pre className="mt-3 overflow-x-auto whitespace-pre-wrap rounded-lg bg-slate-950/70 p-4 text-xs leading-relaxed text-slate-300">
                {payload.report_text}
              </pre>
            </details>
          )}
        </div>
      )}

      {tab === "evidence" && (
        <div className="flex flex-col gap-5">
          <CommitTimeline payload={payload} />
          <EvidenceList evidence={payload.evidence} highlightId={highlightId} />
          <ReadmeClaims claims={payload.readme_claims} />
        </div>
      )}

      {tab === "interview" && (
        <InterviewProbes
          probes={payload.interview_probes}
          evidence={payload.evidence}
          onJump={jump}
        />
      )}
    </div>
  );
}
