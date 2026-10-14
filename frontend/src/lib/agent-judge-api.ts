import { apiFetch } from "./api";

export interface Citation { idx: number; quote: string }
export type ClaimStatus = "verified" | "contradicted" | "unverifiable";
export interface Claim { id: string; text: string; step_idx: number | null; status: ClaimStatus; evidence: Citation[]; external: string[] }
export interface Finding {
  kind: "check" | "claim"; ref: string; task: string; forked: boolean;
  finding: { verdict: "supports" | "contradicts" | "insufficient"; confidence: number | null; evidence: Citation[]; external: string[]; summary: string };
}
export interface JudgeAnswer { type: string; probabilities: Record<string, number>; rationale: string }
export interface InvestigationReport {
  answers: Record<string, JudgeAnswer>;
  claims: Claim[];
  findings: Finding[];
  budget: { claims: number; forks: number; worker_turns: number };
  usage: { input_tokens: number; output_tokens: number; worker_calls: number; workers: number; forks: number; tool_calls: { tool: string; args: unknown }[] };
  steps: number;
}
export interface JudgeReport {
  id: string; model_id: string | null; model_name: string | null; version_id: string | null; trace_id: string | null;
  status: "running" | "done" | "failed"; error: string | null; created_at: string; finished_at: string | null;
  report: InvestigationReport | null;
}

const BASE = "/api/v1/agent-judge";
export const startInvestigation = (traceId: string) =>
  apiFetch<{ id: string; status: "running" }>(`${BASE}/investigations`, { method: "POST", body: JSON.stringify({ trace_id: traceId }) });
export const traceJudgeReports = (traceId: string) => apiFetch<{ reports: JudgeReport[] }>(`${BASE}/traces/${traceId}/reports`);
export const getJudgeReport = (id: string) => apiFetch<JudgeReport>(`${BASE}/reports/${id}`);
