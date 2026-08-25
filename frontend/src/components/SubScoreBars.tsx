import {
  Bar,
  BarChart,
  Cell,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import type { AnalysisPayload, Rules, SubScoreKey } from "../api/client";
import { SUBSCORE_META, pct, suspicionColor } from "../lib/format";

const ORDER: SubScoreKey[] = [
  "clone_similarity",
  "registry_match",
  "readme_consistency",
  "commit_forensics",
];

const DEFAULT_WEIGHTS: Record<SubScoreKey, number> = {
  clone_similarity: 0.45,
  registry_match: 0.2,
  readme_consistency: 0.2,
  commit_forensics: 0.15,
};

interface Row {
  key: SubScoreKey;
  label: string;
  value: number;
  weight: number;
  contribution: number;
}

function ChartTooltip({ active, payload }: any) {
  if (!active || !payload?.length) return null;
  const row: Row = payload[0].payload;
  return (
    <div className="rounded-lg border border-slate-700 bg-slate-900 px-3 py-2 text-xs shadow-xl">
      <div className="font-semibold text-slate-100">{row.label}</div>
      <div className="mt-1 text-slate-400">{SUBSCORE_META[row.key].blurb}</div>
      <div className="mt-1 text-slate-300">
        suspicion <span className="tabular-nums">{row.value.toFixed(2)}</span> ×
        weight <span className="tabular-nums">{row.weight}</span> ={" "}
        <span className="tabular-nums text-slate-100">
          {row.contribution.toFixed(3)}
        </span>
      </div>
    </div>
  );
}

export default function SubScoreBars({
  payload,
  rules,
}: {
  payload: AnalysisPayload;
  rules: Rules | null;
}) {
  const weights = rules?.weights ?? DEFAULT_WEIGHTS;
  const data: Row[] = ORDER.map((key) => {
    const value = payload.sub_scores[key] ?? 0;
    const weight = weights[key] ?? DEFAULT_WEIGHTS[key];
    return { key, label: SUBSCORE_META[key].label, value, weight, contribution: value * weight };
  });

  return (
    <section className="card animate-fade-up">
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-semibold text-slate-200">Signal breakdown</h3>
        <span className="text-xs text-slate-500">
          suspicion 0–1 · higher = more inauthentic
        </span>
      </div>

      <div className="mt-4 h-56 w-full">
        <ResponsiveContainer width="100%" height="100%">
          <BarChart
            data={data}
            layout="vertical"
            margin={{ top: 4, right: 16, bottom: 4, left: 8 }}
            barCategoryGap={12}
          >
            <XAxis
              type="number"
              domain={[0, 1]}
              ticks={[0, 0.25, 0.5, 0.75, 1]}
              tick={{ fill: "#94a3b8", fontSize: 11 }}
              stroke="#334155"
            />
            <YAxis
              type="category"
              dataKey="label"
              width={130}
              tick={{ fill: "#cbd5e1", fontSize: 12 }}
              stroke="#334155"
            />
            <Tooltip cursor={{ fill: "rgba(148,163,184,0.08)" }} content={<ChartTooltip />} />
            <Bar dataKey="value" radius={[0, 4, 4, 0]} isAnimationActive={false}>
              {data.map((row) => (
                <Cell key={row.key} fill={suspicionColor(row.value)} />
              ))}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </div>

      <div className="mt-2 grid grid-cols-1 gap-2 sm:grid-cols-2">
        {data.map((row) => (
          <div
            key={row.key}
            className="flex items-center justify-between rounded-lg border border-slate-800 bg-slate-950/40 px-3 py-2 text-xs"
          >
            <span className="text-slate-300">{row.label}</span>
            <span className="tabular-nums text-slate-400">
              {pct(row.value)} × {row.weight} ={" "}
              <span className="text-slate-200">{row.contribution.toFixed(3)}</span>
            </span>
          </div>
        ))}
      </div>
    </section>
  );
}
