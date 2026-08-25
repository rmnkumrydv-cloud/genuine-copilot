import type { EvidenceItem, SubScoreKey } from "../api/client";
import { SUBSCORE_META } from "../lib/format";
import EvidenceCard from "./EvidenceCard";
import { EmptyState } from "./ui";

const GROUP_ORDER: SubScoreKey[] = [
  "clone_similarity",
  "registry_match",
  "readme_consistency",
  "commit_forensics",
];

export default function EvidenceList({
  evidence,
  highlightId,
}: {
  evidence: EvidenceItem[];
  highlightId?: string | null;
}) {
  if (!evidence.length) {
    return (
      <EmptyState title="No evidence surfaced">
        Nothing crossed the reporting threshold. Signals only emit an evidence
        card when they actually fire — silence here is a genuine result, not a
        gap.
      </EmptyState>
    );
  }

  const groups = GROUP_ORDER.map((key) => ({
    key,
    label: SUBSCORE_META[key].label,
    items: evidence.filter((e) => e.feeds === key),
  })).filter((g) => g.items.length > 0);

  return (
    <div className="flex flex-col gap-6">
      {groups.map((group) => (
        <section key={group.key}>
          <div className="mb-2 flex items-center gap-2">
            <h3 className="section-title">{group.label}</h3>
            <span className="text-xs text-slate-600">
              {group.items.length} item{group.items.length > 1 ? "s" : ""}
            </span>
          </div>
          <div className="grid grid-cols-1 gap-3 lg:grid-cols-2">
            {group.items.map((item) => (
              <EvidenceCard
                key={item.id}
                item={item}
                highlighted={highlightId === item.id}
              />
            ))}
          </div>
        </section>
      ))}
    </div>
  );
}
