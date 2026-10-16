import { apiFetch } from "./api";

export interface TasteExample {
  id: string;
  label: string;
  suggested_label: string;
  reviewed: boolean;
  usable: boolean;
  label_status:
    | "from_feedback"
    | "confirmed"
    | "uncertain"
    | "model_guess"
    | "skipped";
  needs_clarification: boolean;
  reason: string;
  note: string;
  quote: string;
  scope?: string;
  partition: string;
  source: string;
  reference: boolean;
  coverage: Record<string, unknown>;
}
export interface TasteTrial {
  id: string;
  number: number;
  task: string;
  brief: string;
  method: string;
  methodLabel: string;
  status: string;
  score: number | null;
  grader_version: string | null;
  image: string | null;
  humanLabel: string | null;
}
export interface TasteJob {
  id: string;
  operation: string;
  status: string;
  progress: string;
  result: Record<string, unknown> | null;
}
export interface TasteSource {
  kind: string;
  id: string;
  title?: string;
  snippet?: string;
  match_offset?: number;
}
export interface TasteWorkspace {
  id: string;
  name: string;
  model_id?: string;
  wizard_session_id?: string;
  published?: boolean;
  fresh_start?: boolean;
  revision: number;
  fitted_revision: number;
  reviewed: number;
  labels: {
    usable: number;
    from_feedback: number;
    needs_clarification: number;
    model_guesses: number;
    liked: number;
    disliked: number;
    build_gaps: string[];
    partitions: Record<string, Record<string, number>>;
  };
  examples: TasteExample[];
  blockers: string[];
  related_eval_ids: string[];
  endpoint: {
    ready: boolean;
    path: string | null;
    quality_note: string | null;
  };
  grader: {
    version: string | null;
    released: boolean;
    parameters: number;
    limitations: string[];
    metrics: Record<string, { n: number; accuracy: number | null }> | null;
    spec: Record<string, unknown> | null;
    preferences?: TastePreference[];
    examples?: { liked: number; disliked: number } | null;
  };
  search_coverage: {
    recorded_has_more?: boolean;
    recorded_next_offset?: number;
    next_event_offset?: number;
    local?: {
      has_more?: boolean;
      next_offset?: number;
      next_event_offset?: number;
    };
  };
  collection_progress: Record<string, number>;
  trials: TasteTrial[];
  jobs: TasteJob[];
  skill: string;
  history: { connected: boolean };
  sources: TasteSource[];
  cloud_enabled: boolean;
  predictions: TastePrediction[];
  /** Server runs in demo mode: Claude grades check-ins against learned preferences. */
  demo?: boolean;
}
export interface TasteFix {
  issue: string;
  fix: string;
}
export interface TastePrediction {
  id: string;
  version: string;
  output: {
    label: string;
    score: number;
    summary?: string;
    fixes?: TasteFix[];
    keep?: string[];
    brief?: string;
    ref?: string | null;
    screenshot_sha256?: string;
    coverage?: { complete?: boolean; supplied_steps?: number };
  };
  feedback: string | null;
  created_at: string;
}
export interface TastePreference {
  rule: string;
  kind: "prefer" | "avoid";
  evidence: string[];
  /** "feedback" when the user stated the rule directly. */
  source?: string;
}
const base = "/api/v1/taste";
export const tasteGet = () => apiFetch<TasteWorkspace | null>(base);
export const tasteReset = (sessionId: string) =>
  apiFetch<{ session_id: string; archived: boolean }>(`${base}/reset`, {
    method: "POST",
    body: JSON.stringify({ session_id: sessionId }),
  });
export const tasteCreate = () =>
  apiFetch<TasteWorkspace>(base, { method: "POST" });
export const tasteUploadTraces = (
  sessionId: string,
  files: { name: string; content: string }[],
) =>
  apiFetch<{ session_id: string; model_id: string; job_id: string }>(
    `${base}/traces`,
    { method: "POST", body: JSON.stringify({ session_id: sessionId, files }) },
  );
export const tasteReview = (id: string, label: string, note: string) =>
  apiFetch<TasteWorkspace>(`${base}/examples/${id}`, {
    method: "PATCH",
    body: JSON.stringify({ label, note }),
  });
export const tasteStart = (
  operation: string,
  input: Record<string, unknown> = {},
) =>
  apiFetch(`${base}/jobs`, {
    method: "POST",
    body: JSON.stringify({ operation, ...input }),
  });
export const tasteInspect = (kind: string, id: string) =>
  apiFetch<Record<string, unknown>>(`${base}/inspect/${kind}/${id}`);
export const tasteImage = (kind: string, id: string) =>
  apiFetch<{ data_url: string }>(`${base}/images/${kind}/${id}`);
export const tasteCompare = (a: string, b: string, winner: string) =>
  apiFetch(`${base}/comparisons`, {
    method: "POST",
    body: JSON.stringify({ a, b, winner }),
  });

export const tasteCheckSaved = (id: string) =>
  apiFetch<{ label: string; score: number; version: string }>(
    `${base}/check-design/${id}`,
    { method: "POST" },
  );
export const tasteCheckpoint = (id: string) =>
  apiFetch<Record<string, unknown>>(`${base}/checks/${id}`);

export interface HillClimbRound {
  round: number;
  screenshot_sha256: string;
  score: number;
  approved: boolean;
  summary: string;
  fixes: TasteFix[];
  keep: string[];
}
export interface HillClimbArm {
  status: "running" | "done" | "failed";
  working?: string;
  error?: string;
  rounds: HillClimbRound[];
}
export interface HillClimbState {
  brief: string;
  status: "running" | "done" | "failed";
  threshold: number;
  arms: { grader: HillClimbArm; alone: HillClimbArm };
}
export const tasteHillClimb = (brief: string) =>
  apiFetch<{ job_id: string }>(`${base}/hillclimb`, {
    method: "POST",
    body: JSON.stringify({ brief }),
  });
export const tasteHillClimbState = (jobId: string) =>
  apiFetch<HillClimbState>(`${base}/hillclimb/${jobId}`);
export const tasteAddExamples = (
  sessionId: string,
  files: { name: string; label: "liked" | "disliked"; content: string; url?: string }[],
) =>
  apiFetch<{ model_id: string; added: { liked: number; disliked: number }; job_id: string | null }>(
    `${base}/examples`,
    { method: "POST", body: JSON.stringify({ session_id: sessionId, files }) },
  );
