import {
  CartesianGrid,
  ResponsiveContainer,
  Scatter,
  ScatterChart,
  Tooltip,
  XAxis,
  YAxis,
  ZAxis,
} from "recharts";
import type { AnalysisPayload } from "../api/client";
import { EmptyState } from "./ui";

const DAY = 86_400_000;

function PointTooltip({ active, payload }: any) {
  if (!active || !payload?.length) return null;
  const p = payload[0].payload;
  return (
    <div className="max-w-xs rounded-lg border border-slate-700 bg-slate-900 px-3 py-2 text-xs shadow-xl">
      <div className="font-mono text-slate-300">{p.sha}</div>
      <div className="mt-0.5 text-slate-400">{new Date(p.x).toLocaleString()}</div>
      {p.subject && <div className="mt-1 text-slate-200">{p.subject}</div>}
      <div className="mt-1 text-slate-400">
        <span className="text-emerald-400">+{p.additions}</span>{" "}
        <span className="text-red-400">−{p.deletions}</span>
      </div>
    </div>
  );
}

export default function CommitTimeline({ payload }: { payload: AnalysisPayload }) {
  const entries = payload.commit_timeline;

  if (!entries.length) {
    return (
      <section className="card">
        <h3 className="text-sm font-semibold text-slate-200">Commit timeline</h3>
        <div className="mt-3">
          <EmptyState title="No commit history available">
            This repo was analyzed from a snapshot without git metadata, so the
            forensics signal had nothing to score.
          </EmptyState>
        </div>
      </section>
    );
  }

  const points = entries.map((c, i) => ({
    ...c,
    x: new Date(c.ts).getTime(),
    // vertical jitter purely to reduce overplotting of same-day commits
    y: 1 + (((i % 5) - 2) * 0.14),
    churn: c.additions + c.deletions,
  }));

  const times = points.map((p) => p.x);
  const first = Math.min(...times);
  const last = Math.max(...times);
  const spanDays = Math.max(1, Math.round((last - first) / DAY));

  return (
    <section className="card animate-fade-up">
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-semibold text-slate-200">Commit timeline</h3>
        <span className="text-xs text-slate-500">
          {entries.length} commits over ~{spanDays}d · cadence &amp; clustering
        </span>
      </div>

      <div className="mt-4 h-48 w-full">
        <ResponsiveContainer width="100%" height="100%">
          <ScatterChart margin={{ top: 10, right: 16, bottom: 4, left: 8 }}>
            <CartesianGrid stroke="#1e293b" horizontal={false} />
            <XAxis
              type="number"
              dataKey="x"
              domain={["dataMin", "dataMax"]}
              tickFormatter={(ms) => new Date(ms).toLocaleDateString()}
              tick={{ fill: "#94a3b8", fontSize: 11 }}
              stroke="#334155"
            />
            <YAxis
              type="number"
              dataKey="y"
              domain={[0, 2]}
              hide
            />
            <ZAxis type="number" dataKey="churn" range={[40, 340]} />
            <Tooltip cursor={{ strokeDasharray: "3 3" }} content={<PointTooltip />} />
            <Scatter
              data={points}
              fill="#38bdf8"
              fillOpacity={0.7}
              isAnimationActive={false}
            />
          </ScatterChart>
        </ResponsiveContainer>
      </div>

      <p className="mt-2 text-xs text-slate-500">
        Each dot is a commit (size ∝ lines changed). Evenly-spaced dots or a
        vertical stack of same-instant commits are the tells the forensics signal
        looks for.
      </p>
    </section>
  );
}
