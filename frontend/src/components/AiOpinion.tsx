import type { AiOpinion as AiOpinionType } from "../api/client";

export default function AiOpinion({ opinion }: { opinion: AiOpinionType }) {
  return (
    <section className="animate-fade-up rounded-xl border border-dashed border-violet-500/40 bg-violet-500/[0.06] p-5">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <span className="chip border-violet-400/50 bg-violet-500/15 text-violet-200">
            ✦ AI — {opinion.label.replace("_", " ")}
          </span>
        </div>
        <code className="text-[11px] text-violet-300/70">{opinion.review_id}</code>
      </div>

      <div className="mt-3 rounded-lg border border-violet-500/20 bg-violet-950/20 px-3 py-2 text-[11px] text-violet-200/90">
        This note is written <strong>after</strong> the verdict and cannot change
        it. The model saw only the score and evidence summaries — never your source
        or README.
      </div>

      <p className="mt-3 whitespace-pre-wrap text-sm leading-relaxed text-slate-200">
        {opinion.summary}
      </p>

      <p className="mt-3 text-[11px] text-slate-500">source: {opinion.source}</p>
    </section>
  );
}
