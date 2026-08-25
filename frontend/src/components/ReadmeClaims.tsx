import type { ClaimType, ReadmeClaim } from "../api/client";
import { CLAIM_STATUS_META, CLAIM_TYPE_LABEL } from "../lib/format";
import { EmptyState } from "./ui";

const TYPE_ORDER: ClaimType[] = ["tech_stack", "feature", "setup_env"];

export default function ReadmeClaims({ claims }: { claims: ReadmeClaim[] }) {
  if (!claims.length) {
    return (
      <EmptyState title="No README claims extracted">
        Either the repo has no README, or it makes no checkable tech / feature /
        setup claims.
      </EmptyState>
    );
  }

  const counts = claims.reduce<Record<string, number>>((acc, c) => {
    acc[c.verification_status] = (acc[c.verification_status] ?? 0) + 1;
    return acc;
  }, {});

  const groups = TYPE_ORDER.map((type) => ({
    type,
    items: claims.filter((c) => c.claim_type === type),
  })).filter((g) => g.items.length > 0);

  return (
    <section className="card animate-fade-up">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h3 className="text-sm font-semibold text-slate-200">README claims</h3>
        <div className="flex gap-2">
          {(["verified", "contradicted", "unverified"] as const).map((s) =>
            counts[s] ? (
              <span key={s} className={`chip ${CLAIM_STATUS_META[s].classes}`}>
                {counts[s]} {CLAIM_STATUS_META[s].label.toLowerCase()}
              </span>
            ) : null,
          )}
        </div>
      </div>

      <div className="mt-4 flex flex-col gap-5">
        {groups.map((group) => (
          <div key={group.type}>
            <div className="section-title mb-2">{CLAIM_TYPE_LABEL[group.type]}</div>
            <div className="overflow-hidden rounded-lg border border-slate-800">
              <table className="w-full text-sm">
                <tbody>
                  {group.items.map((c, i) => {
                    const meta = CLAIM_STATUS_META[c.verification_status];
                    return (
                      <tr
                        key={i}
                        className="border-b border-slate-800/70 last:border-0"
                      >
                        <td className="px-3 py-2 align-top text-slate-200">
                          {c.claim_text}
                        </td>
                        <td className="w-32 px-3 py-2 align-top">
                          <span className={`chip ${meta.classes}`}>{meta.label}</span>
                        </td>
                        <td className="w-44 px-3 py-2 align-top">
                          {c.evidence_ref ? (
                            <code className="text-[11px] text-sky-300/90">
                              {c.evidence_ref}
                            </code>
                          ) : (
                            <span className="text-[11px] text-slate-600">
                              no citation
                            </span>
                          )}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </div>
        ))}
      </div>

      <p className="mt-3 text-xs text-slate-500">
        Only <span className="text-red-300">contradicted</span> tech-stack claims
        raise suspicion. Features/setup are grounded to code for citations but are
        advisory — an unverified claim is never treated as a lie.
      </p>
    </section>
  );
}
