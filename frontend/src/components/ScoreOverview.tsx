import type { AnalysisPayload, Rules } from "../api/client";
import { VERDICT_META, pct, suspicionColor } from "../lib/format";
import VerdictBadge from "./VerdictBadge";
import { Meter, Stat } from "./ui";

export default function ScoreOverview({
  payload,
  rules,
}: {
  payload: AnalysisPayload;
  rules: Rules | null;
}) {
  const meta = VERDICT_META[payload.verdict];
  const flagged = rules?.thresholds.flagged ?? 0.65;
  const reviewLow = rules?.thresholds.review_low ?? 0.45;
  const composite = payload.composite_score;

  return (
    <section className="card animate-fade-up">
      <div className="flex flex-col gap-6 md:flex-row md:items-center md:justify-between">
        <div className="flex-1">
          <div className="section-title">Composite suspicion</div>
          <div className="mt-1 flex items-baseline gap-3">
            <span
              className="text-5xl font-bold tabular-nums"
              style={{ color: suspicionColor(composite) }}
            >
              {composite.toFixed(2)}
            </span>
            <span className="text-sm text-slate-400">/ 1.00</span>
          </div>

          <div className="mt-4">
            <Meter
              value={composite}
              color={suspicionColor(composite)}
              markers={[
                { at: reviewLow, label: `review ≥ ${reviewLow}` },
                { at: flagged, label: `flag ≥ ${flagged}` },
              ]}
            />
            <div className="mt-1 flex justify-between text-[11px] text-slate-500">
              <span>0 — authentic</span>
              <span>review ≥ {reviewLow}</span>
              <span>flag ≥ {flagged}</span>
              <span>1 — inauthentic</span>
            </div>
          </div>
        </div>

        <div className="flex flex-col items-start gap-2 md:w-72">
          <VerdictBadge verdict={payload.verdict} size="lg" />
          <p className={`text-sm ${meta.accent}`}>{meta.blurb}</p>
          <p className="text-xs text-slate-500">
            Weighted sum of four deterministic signals — reproducible and
            auditable. No model influenced this number.
          </p>
        </div>
      </div>

      <div className="mt-6 grid grid-cols-2 gap-3 sm:grid-cols-4">
        <Stat
          label="Coverage"
          value={pct(payload.coverage_ratio)}
          sub={`${payload.compared_loc} / ${payload.total_loc} LOC compared`}
        />
        <Stat label="Commits" value={payload.commit_count} sub="history depth" />
        <Stat
          label="Evidence"
          value={payload.evidence.length}
          sub="items surfaced"
        />
        <Stat
          label="Matcher"
          value={<span className="text-base">{payload.matcher || "—"}</span>}
          sub="clone engine"
        />
      </div>
    </section>
  );
}
