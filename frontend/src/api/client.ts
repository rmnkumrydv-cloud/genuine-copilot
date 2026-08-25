import axios from "axios";

// Dev: Vite proxies /api -> http://127.0.0.1:8000. Prod: set VITE_API_BASE.
const baseURL = import.meta.env.VITE_API_BASE ?? "/api";

export const http = axios.create({ baseURL, timeout: 120_000 });

// --------------------------------------------------------------------------- //
// Types — mirror genuine/pipeline.py to_payload() and the API endpoints.       //
// --------------------------------------------------------------------------- //
export type Verdict =
  | "clean"
  | "flagged"
  | "insufficient_signal"
  | "needs_human_review";

export type SubScoreKey =
  | "clone_similarity"
  | "readme_consistency"
  | "commit_forensics"
  | "registry_match";

export type SubScores = Record<SubScoreKey, number>;

export type EvidenceType =
  | "clone_match"
  | "readme_contradiction"
  | "commit_anomaly"
  | "registry_match";

export interface EvidenceItem {
  id: string;
  type: EvidenceType;
  feeds: SubScoreKey;
  summary: string;
  detail: Record<string, unknown>;
  confidence: number;
}

export type ClaimType = "tech_stack" | "feature" | "setup_env";
export type VerificationStatus = "verified" | "unverified" | "contradicted";

export interface ReadmeClaim {
  claim_text: string;
  claim_type: ClaimType;
  verification_status: VerificationStatus;
  evidence_ref: string | null;
}

export interface CommitTimelineEntry {
  sha: string;
  ts: string;
  additions: number;
  deletions: number;
  subject: string;
}

export interface InterviewProbe {
  question: string;
  targets_evidence_id: string;
}

export interface AiOpinion {
  review_id: string;
  summary: string;
  label: string;
  source: string;
}

export interface AnalysisPayload {
  repo_url: string;
  owner: string;
  repo_name: string;
  verdict: Verdict;
  composite_score: number;
  sub_scores: SubScores;
  coverage_ratio: number;
  commit_count: number;
  total_loc: number;
  compared_loc: number;
  evidence: EvidenceItem[];
  readme_claims: ReadmeClaim[];
  commit_timeline: CommitTimelineEntry[];
  self_excluded_candidates: string[];
  matcher: string;
  report_text: string;
  ai_opinion: AiOpinion | null;
  interview_probes: InterviewProbe[];
  job_id?: string;
}

export interface Rules {
  weights: SubScores;
  thresholds: { flagged: number; review_low: number };
  insufficient_signal: { min_commits: number; min_coverage: number };
  note: string;
}

export interface Health {
  status: string;
  github_auth: boolean;
  llm_configured: boolean;
}

export interface JobSummary {
  job_id: string;
  repo_url: string;
  status: string;
  created_at: string;
  updated_at: string;
  verdict: Verdict | null;
  composite_score: number | null;
  repo_name: string;
  error: string | null;
}

export interface JobDetail {
  job_id: string;
  repo_url: string;
  status: string;
  result?: AnalysisPayload;
  error?: string;
}

// --------------------------------------------------------------------------- //
// Calls                                                                        //
// --------------------------------------------------------------------------- //
export async function analyzeRepo(
  repoUrl: string,
  explain: boolean,
): Promise<AnalysisPayload> {
  const { data } = await http.post<AnalysisPayload>("/analyze", {
    repo_url: repoUrl,
    explain,
  });
  return data;
}

export async function getRules(): Promise<Rules> {
  const { data } = await http.get<Rules>("/rules");
  return data;
}

export async function getHealth(): Promise<Health> {
  const { data } = await http.get<Health>("/health");
  return data;
}

export async function listJobs(status?: Verdict): Promise<JobSummary[]> {
  const { data } = await http.get<{ jobs: JobSummary[] }>("/jobs", {
    params: status ? { status } : undefined,
  });
  return data.jobs;
}

export async function getJob(jobId: string): Promise<JobDetail> {
  const { data } = await http.get<JobDetail>(`/jobs/${jobId}`);
  return data;
}

/** Best-effort human message out of an axios/network error. */
export function errorMessage(err: unknown): string {
  if (axios.isAxiosError(err)) {
    const detail = (err.response?.data as { detail?: string } | undefined)?.detail;
    if (detail) return detail;
    if (err.code === "ERR_NETWORK")
      return "Cannot reach the Genuine API. Is `uvicorn genuine.api:app` running on :8000?";
    return err.message;
  }
  return err instanceof Error ? err.message : String(err);
}
