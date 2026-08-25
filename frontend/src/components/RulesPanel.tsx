import type { Rules, SubScoreKey } from "../api/client";
import { SUBSCORE_META } from "../lib/format";

const ORDER: SubScoreKey[] = [
  "clone_similarity",
  "registry_match",
  "readme_consistency",
  "commit_forensics",
];

export default function RulesPanel({ rules }: { rules: Rules | null }) {
  return (
    <details className="card group">
      <summary className="flex cursor-pointer list-none items-center justify-between">
        <span className="text-sm font-semibold text-slate-200">
          How this verdict was scored
        </span>
        <span className="text-xs text-slate-500 group-open:hidden">show rulebook ▾</span>
        <span className="hidden text-xs text-slate-500 group-open:inline">hide ▴</span>
      </summary>

      {!rules ? (
        <p className="mt-3 text-sm text-slate-500">Loading the active rulebook…</p>
      ) : (
        <div className="mt-4 grid gap-5 md:grid-cols-2">
          <div>
            <div className="section-title mb-2">Weights (sum = 1.0)</div>
            <div className="flex flex-col gap-2">
              {ORDER.map((key) => {
                const w = rules.weights[key] ?? 0;
                return (
                  <div key={key} className="text-xs">
                    <div className="mb-0.5 flex justify-between">
                      <span className="text-slate-300">{SUBSCORE_META[key].label}</span>
                      <span className="tabular-nums text-slate-400">{w}</span>
                    </div>
                    <div className="h-1.5 w-full rounded-full bg-slate-800">
                      <div
                        className="h-1.5 rounded-full bg-sky-500/70"
                        style={{ width: `${w * 100}%` }}
                      />
                    </div>
                  </div>
                );
              })}
            </div>
          </div>

          <div className="flex flex-col gap-3 text-xs text-slate-300">
            <div>
              <div className="section-title mb-2">Verdict thresholds</div>
              <ul className="space-y-1">
                <li>
                  composite ≥{" "}
                  <span className="tabular-nums text-red-300">
                    {rules.thresholds.flagged}
                  </span>{" "}
                  → flagged
                </li>
                <li>
                  <span className="tabular-nums text-amber-300">
                    {rules.thresholds.review_low}
                  </span>{" "}
                  ≤ composite &lt; {rules.thresholds.flagged} → needs human review
                </li>
                <li>
                  thin history/coverage &amp; low composite → insufficient signal
                </li>
              </ul>
            </div>
            <div>
              <div className="section-title mb-2">Insufficient-signal floor</div>
              <p>
                &lt; {rules.insufficient_signal.min_commits} commits or &lt;{" "}
                {Math.round(rules.insufficient_signal.min_coverage * 100)}% coverage
                → never flagged on pattern alone.
              </p>
            </div>
            <p className="text-slate-500">{rules.note}</p>
          </div>
        </div>
      )}
    </details>
  );
}
