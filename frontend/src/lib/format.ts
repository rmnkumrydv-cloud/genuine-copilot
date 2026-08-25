import type {
  ClaimType,
  EvidenceType,
  SubScoreKey,
  VerificationStatus,
  Verdict,
} from "../api/client";

export interface VerdictMeta {
  label: string;
  blurb: string;
  /** Full Tailwind class strings (kept literal so the scanner emits them). */
  badge: string;
  dot: string;
  ring: string;
  accent: string;
}

export const VERDICT_META: Record<Verdict, VerdictMeta> = {
  clean: {
    label: "Clean",
    blurb: "No signal of copied code, faked history, or false claims.",
    badge: "border-emerald-500/40 bg-emerald-500/10 text-emerald-300",
    dot: "bg-emerald-400",
    ring: "ring-emerald-500/30",
    accent: "text-emerald-300",
  },
  flagged: {
    label: "Flagged",
    blurb: "Strong, decisive signal of inauthentic work.",
    badge: "border-red-500/40 bg-red-500/10 text-red-300",
    dot: "bg-red-400",
    ring: "ring-red-500/30",
    accent: "text-red-300",
  },
  needs_human_review: {
    label: "Needs human review",
    blurb: "Borderline — routed to the queue with evidence pre-assembled.",
    badge: "border-amber-500/40 bg-amber-500/10 text-amber-300",
    dot: "bg-amber-400",
    ring: "ring-amber-500/30",
    accent: "text-amber-300",
  },
  insufficient_signal: {
    label: "Insufficient signal",
    blurb: "Too little history or coverage to judge — never a false accusation.",
    badge: "border-slate-500/40 bg-slate-500/10 text-slate-300",
    dot: "bg-slate-400",
    ring: "ring-slate-500/30",
    accent: "text-slate-300",
  },
};

export const SUBSCORE_META: Record<
  SubScoreKey,
  { label: string; blurb: string }
> = {
  clone_similarity: {
    label: "Clone similarity",
    blurb: "Copied code vs. candidate repos (logic-level, rename-resistant).",
  },
  registry_match: {
    label: "Registry match",
    blurb: "Near-duplicate of another submission (MinHash fingerprint).",
  },
  readme_consistency: {
    label: "README consistency",
    blurb: "Tech-stack claims contradicted by the actual code.",
  },
  commit_forensics: {
    label: "Commit forensics",
    blurb: "Fabricated / dumped commit history (timing, messages, collisions).",
  },
};

export const EVIDENCE_META: Record<
  EvidenceType,
  { label: string; glyph: string; classes: string }
> = {
  clone_match: {
    label: "Clone match",
    glyph: "⧉",
    classes: "border-red-500/30 text-red-300",
  },
  registry_match: {
    label: "Registry match",
    glyph: "≣",
    classes: "border-fuchsia-500/30 text-fuchsia-300",
  },
  readme_contradiction: {
    label: "README contradiction",
    glyph: "≠",
    classes: "border-amber-500/30 text-amber-300",
  },
  commit_anomaly: {
    label: "Commit anomaly",
    glyph: "◔",
    classes: "border-sky-500/30 text-sky-300",
  },
};

export const CLAIM_STATUS_META: Record<
  VerificationStatus,
  { label: string; classes: string }
> = {
  verified: {
    label: "Verified",
    classes: "border-emerald-500/40 bg-emerald-500/10 text-emerald-300",
  },
  contradicted: {
    label: "Contradicted",
    classes: "border-red-500/40 bg-red-500/10 text-red-300",
  },
  unverified: {
    label: "Unverified",
    classes: "border-slate-600/50 bg-slate-700/20 text-slate-300",
  },
};

export const CLAIM_TYPE_LABEL: Record<ClaimType, string> = {
  tech_stack: "Tech stack",
  feature: "Feature",
  setup_env: "Setup",
};

export function pct(x: number, digits = 0): string {
  return `${(x * 100).toFixed(digits)}%`;
}

/** Suspicion → bar color. Higher suspicion = hotter. */
export function suspicionColor(x: number): string {
  if (x >= 0.65) return "#ef4444"; // red
  if (x >= 0.45) return "#f59e0b"; // amber
  if (x >= 0.2) return "#eab308"; // yellow
  return "#10b981"; // emerald
}

export function shortRepo(p: AnalysisIdentity): string {
  if (p.repo_name) return p.owner ? `${p.owner}/${p.repo_name}` : p.repo_name;
  return p.repo_url;
}

interface AnalysisIdentity {
  owner?: string;
  repo_name?: string;
  repo_url: string;
}

export function formatDateTime(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleString(undefined, {
    year: "numeric",
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}
