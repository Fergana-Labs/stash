import { apiFetch } from "./api";

const BASE = "/api/v1/rm/optimizations";
export interface BusinessMetric { name: string; unit: string; direction: "higher" | "lower"; minimum: number; maximum: number; regression_tolerance: number }
export interface Optimization {
  id: string; name: string; agent: string; scope: string; reward_model_id: string;
  reward_model_name?: string; metric: BusinessMetric; status: string; active_revision_id: string;
  runs_per_arm: number; max_rounds: number; run_count?: number; error: string | null; created_at: string;
}
export interface PromptRevision { id: string; version: number; content: string; rationale: string; created_at: string }
export interface Estimate { n: number; mean: number | null; low: number | null; high: number | null }
export interface Comparison {
  ready: boolean; promote: boolean; reason: string; required_per_arm: number;
  arms: Record<string, { assigned: number; completed: number; reward: Estimate; business: Estimate }>;
  reward_change?: Omit<Estimate, "n">; business_change?: Omit<Estimate, "n">;
}
export interface OptimizationRound { id: string; number: number; baseline_id: string; candidate_id: string | null; status: string; error: string | null; report: Comparison | null }
export interface OptimizationRun {
  id: string; revision_id: string; round_id: string | null; work_key: string; agent_version: string;
  arm: string; status: string; trace_id: string | null; reward: number | null; outcome: number | null;
  outcome_source: string | null; error: string | null; assigned_at: string;
}
export interface Trend { day: string; revision_id: string; assigned: number; scored: number; measured: number; reward: number | null; business: number | null }
export interface OptimizationDetail extends Optimization {
  reward_model: { id: string; name: string; status: string; error: string | null };
  revisions: PromptRevision[]; rounds: OptimizationRound[]; runs: OptimizationRun[]; trends: Trend[];
  events: { kind: string; detail: Record<string, unknown>; created_at: string }[];
}
export interface CreateOptimization { name: string; reward_model_id: string; agent: string; scope: string; initial_prompt: string; metric: BusinessMetric; runs_per_arm: number; max_rounds: number }
export function listOptimizations(): Promise<Optimization[]> { return apiFetch(BASE); }
export function getOptimization(id: string): Promise<OptimizationDetail> { return apiFetch(`${BASE}/${id}`); }
export function createOptimization(body: CreateOptimization): Promise<OptimizationDetail> { return apiFetch(BASE, { method: "POST", body: JSON.stringify(body) }); }
export function controlOptimization(id: string, action: "pause" | "resume" | "rollback", revisionId?: string): Promise<OptimizationDetail> { return apiFetch(`${BASE}/${id}/control`, { method: "POST", body: JSON.stringify({ action, revision_id: revisionId }) }); }
export function recordBusinessOutcome(runId: string, value: number, source: string): Promise<unknown> { return apiFetch(`${BASE}/runs/${runId}/outcome`, { method: "POST", body: JSON.stringify({ value, source }) }); }
export function abandonOptimizationRun(runId: string, reason: string): Promise<unknown> { return apiFetch(`${BASE}/runs/${runId}/abandon`, { method: "POST", body: JSON.stringify({ reason }) }); }
export function getOptimizationRun(runId: string): Promise<Record<string, unknown>> { return apiFetch(`${BASE}/runs/${runId}`); }
