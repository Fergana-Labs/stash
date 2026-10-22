import { apiFetch } from "./api";

export interface MonitoredAgent { agent: string; display_name: string; trace_count: number; last_seen: string | null }
export interface MonitoringModel { id: string; name: string; metrics: { action_scoring_version?: number; trace_scoring_version?: number }; finished_at: string | null }
export interface MonitoringProgram {
  id: string; name: string; agent: string; scope: string; status: string; reward_model_id: string | null; reward_model_name: string | null; intuition_model_id?: string | null; eval_name?: string | null;
  active_revision_id: string; active_version: number; run_count: number; accepted_count: number; error: string | null;
}
export interface MonitoringOverview { agents: MonitoredAgent[]; models: MonitoringModel[]; programs: MonitoringProgram[] }
export interface RewardPoint {
  id: string; trace_id: string | null; title: string; recorded_at: string; reward: number; revision_id: string | null; rolling_mean: number; window_count: number;
}
export interface RewardHistory {
  agent: string; model_id: string; program_id: string | null; active_revision_id: string | null; unit: "action_credit" | "trace_reward" | "eval_probability"; window: number;
  total: number; mean: number | null; current_n: number; current_mean: number | null; previous_n: number; previous_mean: number | null; points: RewardPoint[];
}
const BASE = "/api/v1/rm/optimizations/monitoring";
export function getMonitoring(): Promise<MonitoringOverview> { return apiFetch(BASE); }
export function getRewardHistory(agent: string, modelId: string, window: number, programId?: string): Promise<RewardHistory> {
  const params = new URLSearchParams({ agent, model_id: modelId, window: String(window) });
  if (programId) params.set("program_id", programId);
  return apiFetch(`${BASE}/rewards?${params}`);
}
