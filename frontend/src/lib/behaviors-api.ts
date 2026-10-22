import { apiFetch } from "./api";

export type Actor = "user" | "agent" | "environment";
export type Detector = "rule" | "llm" | "agent_judge";
export type Severity = "low" | "medium" | "high";
export type Verdict = "confirmed" | "rejected";
export type ChannelKind = "slack" | "email";

export interface AlertConfig { threshold: number; window_hours: number; cooldown_hours: number; channels: ChannelKind[] }

export interface Behavior {
  id: string; name: string; slug: string; actor: Actor; definition: string; examples: string[];
  detector: Detector; rule: { kind: string } | null; severity: Severity; enabled: boolean;
  alert: AlertConfig | null; last_alert_at: string | null; eval_id: string | null; version: number;
  created_at: string; updated_at: string; hit_count?: number;
}

export interface BehaviorInput {
  name: string; actor: Actor; detector: Detector; definition: string; examples: string[];
  rule: { kind: string } | null; severity: Severity; enabled: boolean; alert: AlertConfig | null;
}

export interface DayPoint { day: string; hits: number; traces_with_hit: number; traces_scanned: number; rate: number | null }
export interface BehaviorTrend {
  behavior: Behavior; series: DayPoint[]; last_7_days: number; previous_7_days: number; change: number | null; traces_scanned: number;
}
export interface BehaviorOverview { days: number; behaviors: BehaviorTrend[] }

export interface BehaviorAlert { id: string; behavior_id: string; behavior_name: string; message: string; stats: Record<string, unknown>; delivered: unknown; created_at: string; triage_id?: string | null }

export interface SearchSegment { start_idx: number; end_idx: number; score: number | null; snippet: string; quote?: string }
export interface SearchBehavior { id: string; behavior_id: string; name: string; actor: Actor; start_idx: number; end_idx: number; review: Verdict | null; confidence: number | null }
export interface SearchResult {
  trace_id: string; title: string | null; created_at: string; agent: string | null; input: string | null; output: string | null;
  score: number | null; segments: SearchSegment[]; behaviors: SearchBehavior[];
  /** e.g. "answer", "partial_answer", "not_found", "handoff", "error". */
  outcome?: string | null;
  /** The agent's final user-facing answer, clipped. */
  final_output?: string | null;
  session_id?: string | null;
}
export interface SearchResponse { query: string; mode: "semantic" | "text" | "browse"; results: SearchResult[] }

export interface Evidence { idx: number; quote: string }
export interface BehaviorHit {
  id: string; behavior_id: string; trace_id: string; start_idx: number; end_idx: number; confidence: number | null;
  evidence: Evidence[] | null; note: string | null; source: string; review: Verdict | null; created_at: string;
  /** Why the reviewer confirmed or rejected it; the detector learns from it. */
  review_note?: string | null;
  behavior_name?: string; actor?: Actor; severity?: Severity; trace_title?: string | null; trace_created_at?: string;
}

const BASE = "/api/v1/behaviors";
const send = <T,>(path: string, method: string, body?: unknown) =>
  apiFetch<T>(path, { method, ...(body !== undefined && { body: JSON.stringify(body) }) });

export const listBehaviors = () => apiFetch<{ behaviors: Behavior[]; rules: string[] }>(BASE);
export const createBehavior = (body: BehaviorInput) => send<Behavior>(BASE, "POST", body);
export const installStarters = (kinds?: string[]) => send<{ created: Behavior[] }>(`${BASE}/starters`, "POST", kinds ? { kinds } : {});
export const getBehaviorOverview = (days: number) => apiFetch<BehaviorOverview>(`${BASE}/monitoring?days=${days}`);
export const listBehaviorAlerts = () => apiFetch<{ alerts: BehaviorAlert[] }>(`${BASE}/alerts`);

export function searchBehaviorTraces(opts: { q?: string; behaviors?: string[]; agent?: string; days?: number; limit?: number; rerank?: boolean }) {
  const params = new URLSearchParams();
  if (opts.q?.trim()) params.set("q", opts.q.trim());
  for (const id of opts.behaviors ?? []) params.append("behaviors", id);
  if (opts.agent) params.set("agent", opts.agent);
  if (opts.days) params.set("days", String(opts.days));
  if (opts.limit) params.set("limit", String(opts.limit));
  if (opts.rerank) params.set("rerank", "true");
  return apiFetch<SearchResponse>(`${BASE}/search?${params}`);
}

export const traceBehaviorHits = (traceId: string) => apiFetch<{ hits: BehaviorHit[] }>(`${BASE}/traces/${traceId}/hits`);
export const saveWindowsToEval = (body: { eval_id: string; label: string; windows: { trace_id: string; start_idx: number; end_idx: number }[] }) =>
  send<{ examples: unknown[] }>(`${BASE}/datasets`, "POST", body);
export const reviewHit = (hitId: string, verdict: Verdict | null, note = "") => send<BehaviorHit>(`${BASE}/hits/${hitId}/review`, "POST", { verdict, note });

export const getBehavior = (id: string) => apiFetch<Behavior>(`${BASE}/${id}`);
export const updateBehavior = (id: string, changes: Partial<BehaviorInput>) => send<Behavior>(`${BASE}/${id}`, "PATCH", changes);
export const deleteBehavior = (id: string) => send<void>(`${BASE}/${id}`, "DELETE");
export function listBehaviorHits(id: string, opts: { review?: Verdict | "unreviewed"; limit?: number; offset?: number } = {}) {
  const params = new URLSearchParams();
  if (opts.review) params.set("review", opts.review);
  if (opts.limit) params.set("limit", String(opts.limit));
  if (opts.offset) params.set("offset", String(opts.offset));
  return apiFetch<{ hits: BehaviorHit[] }>(`${BASE}/${id}/hits?${params}`);
}
export const addBehaviorHit = (id: string, body: { trace_id: string; start_idx: number; end_idx: number; note?: string }) =>
  send<BehaviorHit>(`${BASE}/${id}/hits`, "POST", body);
export const promoteBehavior = (id: string) => send<{ behavior: Behavior; eval_id: string; examples: number }>(`${BASE}/${id}/promote`, "POST");

export const ACTORS: { value: Actor; label: string }[] = [
  { value: "user", label: "User" }, { value: "agent", label: "Agent" }, { value: "environment", label: "Environment" },
];
export const SEVERITIES: Severity[] = ["low", "medium", "high"];
export const DETECTOR_LABEL: Record<Detector, string> = { llm: "Described in words", rule: "Built-in", agent_judge: "Described in words · verified by the Agent Judge" };

/** "partial_answer" → "Partial answer". Enum values never reach the screen raw. */
export const humanize = (value: string) => {
  const text = value.replaceAll("_", " ").replaceAll("-", " ").trim();
  return text ? text[0].toUpperCase() + text.slice(1) : text;
};

/** One color per actor everywhere (matches the blog): user green, environment blue, agent orange. */
export const ACTOR_COLOR: Record<Actor, { dot: string; chip: string; hex: string }> = {
  user: { dot: "bg-emerald-500", chip: "bg-emerald-500/12 text-emerald-700 dark:text-emerald-300", hex: "#10b981" },
  environment: { dot: "bg-blue-500", chip: "bg-blue-500/12 text-blue-700 dark:text-blue-300", hex: "#3b82f6" },
  agent: { dot: "bg-orange-500", chip: "bg-orange-500/12 text-orange-700 dark:text-orange-300", hex: "#f97316" },
};
/** Steps are stored 0-based; the trace viewer numbers them from 1. */
export const stepWindow = (start: number, end: number) => start === end ? `step ${start + 1}` : `steps ${start + 1}–${end + 1}`;
export const traceStepHref = (traceId: string, start: number) => `/reward-models/traces/${traceId}?step=${start}`;

export type CohortBy = "outcome" | "satisfaction" | "agent" | "behavior" | "tool_use" | "task_type";
export interface Cohort {
  key: string; traces: number; share: number; frustrated_rate: number; correction_rate: number; avg_tool_calls: number;
  outcomes: Record<string, number>; top_behaviors: [string, number][]; sample: { trace_id: string; title: string | null }[];
}
export interface CohortOverview { by: CohortBy; days: number; traces: number; cohorts: Cohort[] }
export const getCohorts = (by: CohortBy, days: number) => apiFetch<CohortOverview>(`${BASE}/cohorts?by=${by}&days=${days}`);
export const COHORT_DIMENSIONS: { value: CohortBy; label: string }[] = [
  { value: "outcome", label: "Outcome" }, { value: "satisfaction", label: "Satisfaction" }, { value: "agent", label: "Agent" },
  { value: "behavior", label: "Behavior" }, { value: "tool_use", label: "Tool use" }, { value: "task_type", label: "Task type" },
];

// --- Templates ---
export interface BehaviorTemplate { slug: string; name: string; actor: Actor; definition: string; examples: string[]; severity: Severity; verify: boolean }
export const listBehaviorTemplates = () => apiFetch<{ templates: BehaviorTemplate[] }>(`${BASE}/templates`);
export const createFromTemplate = (slug: string) => send<Behavior>(`${BASE}/templates/${slug}`, "POST");

// --- Releases ---
export interface Release { id: string; agent: string | null; label: string; released_at: string; note: string | null }
export const listReleases = () => apiFetch<{ releases: Release[] }>(`${BASE}/releases`);
export const createRelease = (body: { agent?: string | null; label: string; released_at?: string; note?: string }) => send<Release>(`${BASE}/releases`, "POST", body);
export const deleteRelease = (id: string) => send<void>(`${BASE}/releases/${id}`, "DELETE");
export interface RateWindow { traces: number; with_hit: number; rate: number | null; ci: [number, number] | null }
export interface ReleaseComparison { release: Release; before: RateWindow; after: RateWindow; change: number | null; significant: boolean; window_days: number }
export const compareAroundRelease = (id: string, releaseId: string) => apiFetch<ReleaseComparison>(`${BASE}/${id}/compare?release_id=${encodeURIComponent(releaseId)}`);

// --- Triage ---
export interface RootCause { title: string; explanation: string; traces: { trace_id: string; title: string | null; step_idx: number | null }[]; share: number | null }
export interface Triage {
  id: string; status: "running" | "done" | "failed"; error: string | null; created_at: string;
  result: { summary: string; root_causes: RootCause[]; suggested_fixes: string[] } | null;
}
export const startTriage = (id: string) => send<{ id: string; status: "running" }>(`${BASE}/${id}/triage`, "POST");
export const getTriage = (id: string) => apiFetch<{ triage: Triage | null }>(`${BASE}/${id}/triage`);
