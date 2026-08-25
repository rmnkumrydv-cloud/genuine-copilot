import type { Verdict } from "../api/client";
import { VERDICT_META } from "../lib/format";

const SIZES = {
  sm: "text-xs px-2.5 py-1",
  md: "text-sm px-3 py-1.5",
  lg: "text-base px-4 py-2",
} as const;

export default function VerdictBadge({
  verdict,
  size = "md",
}: {
  verdict: Verdict;
  size?: keyof typeof SIZES;
}) {
  const m = VERDICT_META[verdict];
  return (
    <span className={`chip ${m.badge} ${SIZES[size]}`}>
      <span className={`h-2 w-2 rounded-full ${m.dot}`} />
      {m.label}
    </span>
  );
}
