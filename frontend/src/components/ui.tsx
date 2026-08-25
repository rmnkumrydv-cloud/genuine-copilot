import type { ReactNode } from "react";

export function Spinner({ label }: { label?: string }) {
  return (
    <div className="flex items-center gap-3 text-slate-400">
      <span className="h-4 w-4 animate-spin rounded-full border-2 border-slate-600 border-t-sky-400" />
      {label && <span className="text-sm">{label}</span>}
    </div>
  );
}

export function Stat({
  label,
  value,
  sub,
}: {
  label: string;
  value: ReactNode;
  sub?: ReactNode;
}) {
  return (
    <div className="card-tight">
      <div className="section-title">{label}</div>
      <div className="mt-1 text-2xl font-semibold tabular-nums text-slate-100">
        {value}
      </div>
      {sub && <div className="mt-0.5 text-xs text-slate-400">{sub}</div>}
    </div>
  );
}

/** Horizontal meter with an optional set of threshold markers. */
export function Meter({
  value,
  color,
  markers = [],
}: {
  value: number;
  color: string;
  markers?: { at: number; label: string }[];
}) {
  const clamped = Math.max(0, Math.min(1, value));
  return (
    <div className="relative h-3 w-full rounded-full bg-slate-800">
      <div
        className="h-3 rounded-full transition-all duration-500"
        style={{ width: `${clamped * 100}%`, backgroundColor: color }}
      />
      {markers.map((m) => (
        <div
          key={m.label}
          className="absolute -top-1 flex flex-col items-center"
          style={{ left: `${m.at * 100}%` }}
          title={m.label}
        >
          <div className="h-5 w-px bg-slate-500" />
        </div>
      ))}
    </div>
  );
}

export function EmptyState({
  title,
  children,
}: {
  title: string;
  children?: ReactNode;
}) {
  return (
    <div className="card flex flex-col items-center justify-center gap-2 py-10 text-center">
      <div className="text-sm font-semibold text-slate-300">{title}</div>
      {children && (
        <div className="max-w-md text-sm text-slate-500">{children}</div>
      )}
    </div>
  );
}
