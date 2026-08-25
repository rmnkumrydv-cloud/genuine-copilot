import { useState } from "react";
import type { ReactNode } from "react";
import type { EvidenceItem } from "../api/client";
import { EVIDENCE_META, pct } from "../lib/format";

function renderValue(v: unknown): ReactNode {
  if (v === null || v === undefined || v === "")
    return <span className="text-slate-500">—</span>;
  if (Array.isArray(v)) {
    if (v.length === 0) return <span className="text-slate-500">none</span>;
    if (v.every((x) => typeof x !== "object")) {
      return (
        <div className="flex flex-wrap gap-1">
          {v.map((x, i) => (
            <code
              key={i}
              className="rounded border border-slate-700 bg-slate-950/60 px-1.5 py-0.5 text-[11px] text-slate-300"
            >
              {String(x)}
            </code>
          ))}
        </div>
      );
    }
    return (
      <pre className="overflow-x-auto rounded bg-slate-950/70 p-2 text-[11px] text-slate-300">
        {JSON.stringify(v, null, 2)}
      </pre>
    );
  }
  if (typeof v === "object")
    return (
      <pre className="overflow-x-auto rounded bg-slate-950/70 p-2 text-[11px] text-slate-300">
        {JSON.stringify(v, null, 2)}
      </pre>
    );
  return <span className="text-slate-200">{String(v)}</span>;
}

export default function EvidenceCard({
  item,
  highlighted,
}: {
  item: EvidenceItem;
  highlighted?: boolean;
}) {
  const [open, setOpen] = useState(false);
  const meta = EVIDENCE_META[item.type];
  const detailEntries = Object.entries(item.detail ?? {});

  return (
    <div
      id={`evidence-${item.id}`}
      className={`card-tight scroll-mt-24 transition-shadow ${
        highlighted ? "ring-2 ring-sky-400/70" : ""
      }`}
    >
      <div className="flex items-start justify-between gap-3">
        <div className="flex items-start gap-2">
          <span className={`chip ${meta.classes}`}>
            <span aria-hidden>{meta.glyph}</span>
            {meta.label}
          </span>
        </div>
        <div className="text-right">
          <div className="text-[11px] uppercase tracking-wide text-slate-500">
            confidence
          </div>
          <div className="text-sm font-semibold tabular-nums text-slate-200">
            {pct(item.confidence)}
          </div>
        </div>
      </div>

      <p className="mt-2 text-sm text-slate-200">{item.summary}</p>

      <div className="mt-2 flex items-center justify-between">
        <code className="text-[11px] text-slate-500">{item.id}</code>
        {detailEntries.length > 0 && (
          <button
            onClick={() => setOpen((o) => !o)}
            className="text-xs text-sky-400 hover:text-sky-300"
          >
            {open ? "Hide detail" : "Show detail"}
          </button>
        )}
      </div>

      {open && detailEntries.length > 0 && (
        <dl className="mt-2 grid grid-cols-1 gap-2 border-t border-slate-800 pt-2">
          {detailEntries.map(([k, v]) => (
            <div key={k} className="grid grid-cols-[9rem_1fr] gap-2 text-xs">
              <dt className="text-slate-500">{k}</dt>
              <dd>{renderValue(v)}</dd>
            </div>
          ))}
        </dl>
      )}
    </div>
  );
}
