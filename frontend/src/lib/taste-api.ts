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
  grader: {
    version: string | null;
    released: boolean;
    parameters: number;
    limitations: string[];
    metrics: Record<string, { n: number; accuracy: number | null }> | null;
    spec: Record<string, unknown> | null;
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
  predictions: {
    id: string;
    version: string;
    output: { label: string; score: number };
    feedback: string | null;
  }[];
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
