import { API_BASE, apiFetch, getAuthToken } from "@/lib/api";
import { getScopeUserId, SCOPE_HEADER } from "@/lib/scope-store";
import type { Evaluation, Example, Gate, Item, LoggedPrediction, Prediction, RubricQuestion } from "@/lib/intuition-api";

/** Client for /api/v1/model-wizard (backend/routers/model_wizard.py). */
const MW = "/api/v1/model-wizard";

export type CardKind = "choices" | "uploader" | "labeler" | "criteria" | "report" | "playground" | "review" | "robustness" | "examples" | "brief" | "inbox" | "golden" | "agreement" | "topics";
export interface Card { id: string; kind: CardKind; props: Record<string, unknown> }
export interface Activity { id: string; tool: string; label: string; status: "running" | "done" | "error"; error?: string | null; progress?: string }
export type AssistantPart = ({ type: "text"; text: string }) | ({ type: "card" } & Card) | ({ type: "activity" } & Activity);
export type TranscriptEntry =
  | { role: "user"; kind: "message" | "event"; text: string }
  | { role: "assistant"; parts: AssistantPart[] };

export interface WizardSession {
  id: string; model_id: string | null; title: string; created_at: string; updated_at: string;
  transcript?: TranscriptEntry[]; model_name?: string | null;
  status: "draft" | "saved"; draft_input?: string;
}

export function wizardSessionName(session: WizardSession): string {
  if (session.model_name) return session.model_name;
  if (!["New model", "New eval", "Untitled eval"].includes(session.title)) return session.title;
  return session.draft_input?.trim().split("\n")[0].slice(0, 100) || "Untitled eval";
}

export interface LeaderboardRow { name: string; detail: string; n: number; accuracy: number | null; log_loss: number | null; ece: number | null; shipping?: boolean }
export interface TrainingReport {
  version: number;
  /** The report belongs to the live version (the draft is untrained or absent): nothing to ship. */
  is_live?: boolean;
  counts: { train: number; held_out: number; labels: Record<string, number> };
  holdout: Pick<Evaluation, "n" | "accuracy" | "log_loss" | "ece" | "confusion" | "rows" | "classification" | "by_difficulty"> & { accuracy_interval: [number, number] | null; reliability: NonNullable<Evaluation["reliability"]> };
  train_accuracy: number | null;
  /** Out-of-fold accuracy on training labels the judge never saw as references. */
  cross_validated: { n: number; accuracy: number | null };
  leaderboard: LeaderboardRow[];
  learning_curve: { n: number; accuracy: number; draws: number }[];
  drivers: { question: string; prompt: string; share: number; kind: "verdict" | "probe" | "criterion" }[];
  probe: { rows: number; loo_accuracy: number; loo_log_loss: number; ridge: number } | null;
  regularization: { l2: number; cv_log_loss: Record<string, number | null> };
  temperature: number;
  gate: Gate;
  warnings: string[];
}

export interface AttackRound { attempts: number; fooled: number; success_rate: number | null; parents: number; parents_broken: number; examples: { example_id: string; label: string; attack: string; p_target: number }[] }
export interface HardenResult {
  target: string; before: AttackRound; found_in_training: AttackRound; after: AttackRound; repairs_added: number;
  holdout_accuracy: { before: number | null; after: number | null }; gate: Gate; note: string;
}
export interface Discovery { insights: { insight: string; question: RubricQuestion }[]; pairs: { a: string; a_label: string; b: string; b_label: string }[] }

const post = <T>(path: string, body?: unknown) =>
  apiFetch<T>(path, { method: "POST", body: body === undefined ? undefined : JSON.stringify(body) });

export const wzSessions = () => apiFetch<{ sessions: WizardSession[] }>(`${MW}/sessions`);
export const wzCreate = (model_id?: string | null) => post<WizardSession>(`${MW}/sessions`, { model_id: model_id ?? null });
export const wzGet = (id: string) => apiFetch<WizardSession>(`${MW}/sessions/${id}`);
export const wzSaveDraft = (id: string, text: string) => apiFetch<{ saved: boolean }>(`${MW}/sessions/${id}/draft`, { method: "PATCH", body: JSON.stringify({ text }), keepalive: true });
export const wzDelete = (id: string) => apiFetch<void>(`${MW}/sessions/${id}`, { method: "DELETE" });
export const wzTrain = (modelId: string) => post<TrainingReport>(`${MW}/models/${modelId}/train`);
export const wzReport = (modelId: string) => apiFetch<{ report: TrainingReport | null }>(`${MW}/models/${modelId}/report`);
export const wzDiscover = (modelId: string, body: { count?: number; guidance?: string } = {}) => post<Discovery>(`${MW}/models/${modelId}/discover`, body);
export const wzHarden = (modelId: string, target_label?: string) => post<HardenResult>(`${MW}/models/${modelId}/harden`, { target_label: target_label ?? null });

// ── Curation: brief, queues, calibration, topics, golden-set health ───────

export interface BriefLabel { id: string; means: string; not?: string }
export interface Brief {
  decision?: string; input?: string; labels?: BriefLabel[]; costly_mistake?: string; must_never?: string[];
  edge_cases?: string[]; context?: string; success?: string; reviewers?: string[];
}
export interface BriefState { brief: Brief; fields: Record<keyof Brief, string>; complete: boolean; missing: (keyof Brief)[]; optional_missing: (keyof Brief)[] }
export type QueueRow = LoggedPrediction & { escalation_note?: string };
export interface ReviewLink { token: string; reviewer: string; created_at: string; rated: number }
export interface AgreementStats { agreement: number; kappa: number | null; n: number }
export interface Agreement {
  calibration_items: number;
  reviewers: { token: string; name: string }[];
  pairs: ({ a: string; b: string } & AgreementStats)[];
  human: AgreementStats | null;
  judge: AgreementStats | null;
  verdict: string | null;
  disagreements: { example_id: string; item: Item; labels: { rater: string; label: string; note: string }[] }[];
}
export interface Topic {
  id: string; name: string; description: string; served: number; unreviewed: number; reviewed: number; overturned: number;
  overturn_rate: number | null; examples: Record<string, number>; held_out: { n: number; accuracy: number | null };
}
export interface Topics { computed_at: string | null; topics: Topic[] }
export interface SimilarPair { a: string; b: string; a_label: string; b_label: string; similarity: number }
export interface Health {
  labeled: number; needs_label: number; pinned: number; calibration: number; by_source: Record<string, number>;
  coverage: { label: string; total: number; held_out: number; pinned: number }[];
  duplicates: SimilarPair[]; lookalikes: SimilarPair[]; issues: string[];
}
export interface ReviewView {
  model: string; reviewer: string; instructions: string; label_boundaries: BriefLabel[] | null;
  labels: { id: string; description: string }[];
  items: { id: string; item: Item; item_b: Item | null; my_label: string | null; my_note: string | null }[];
}

const M = (id: string) => `${MW}/models/${id}`;
export const wzBrief = (id: string) => apiFetch<BriefState>(`${M(id)}/brief`);
export const wzSaveBrief = (id: string, changes: Partial<Record<keyof Brief, unknown>>) => apiFetch<BriefState>(`${M(id)}/brief`, { method: "PATCH", body: JSON.stringify(changes) });
export const wzQueue = (id: string, which: "all" | "triage" | "expert", topic?: string | null) => apiFetch<{ items: QueueRow[] }>(`${M(id)}/queue/${which}${topic ? `?topic=${encodeURIComponent(topic)}` : ""}`);
export const wzTriage = (id: string, predictionId: string, action: "looks_right" | "escalate" | "ignore", note = "") => post<{ status: string; example: Example | null }>(`${M(id)}/predictions/${predictionId}/triage`, { action, note });
export const wzResolve = (id: string, predictionId: string, body: { label: string; note?: string; pin?: boolean }) => post<{ status: string; example: Example | null }>(`${M(id)}/predictions/${predictionId}/resolve`, body);
export const wzCalibration = (id: string, body: { example_ids?: string[] | null; on?: boolean } = {}) => post<{ calibration: number }>(`${M(id)}/calibration`, body);
export const wzAgreement = (id: string) => apiFetch<Agreement>(`${M(id)}/agreement`);
export const wzLinks = (id: string) => apiFetch<{ links: ReviewLink[] }>(`${M(id)}/review-links`);
export const wzCreateLink = (id: string, reviewer: string) => post<ReviewLink>(`${M(id)}/review-links`, { reviewer });
export const wzRevokeLink = (id: string, token: string) => apiFetch<void>(`${M(id)}/review-links/${token}`, { method: "DELETE" });
export const wzTopics = (id: string) => apiFetch<Topics>(`${M(id)}/topics`);
export const wzRefreshTopics = (id: string) => post<Topics>(`${M(id)}/topics`);
export const wzHealth = (id: string) => apiFetch<Health>(`${M(id)}/health`);
export const wzFromCorrections = (id: string, count = 3) => post<Discovery & { reasons: number }>(`${M(id)}/criteria-from-corrections`, { count });
export const reviewLinkUrl = (token: string) => `${typeof window === "undefined" ? "" : window.location.origin}/review/${token}`;

/** Invited reviewers have no account; these calls carry only the link's token. */
async function publicFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}/api/v1/review-links/${path}`, { ...init, headers: { "Content-Type": "application/json" } });
  if (!res.ok) {
    const detail = await res.json().then((b) => b?.detail as string | undefined).catch(() => undefined);
    throw new Error(detail || `Request failed (${res.status})`);
  }
  return res.json() as Promise<T>;
}
export const reviewView = (token: string) => publicFetch<ReviewView>(token);
export const reviewRate = (token: string, exampleId: string, label: string, note = "") =>
  publicFetch<{ rated: boolean }>(`${token}/items/${exampleId}`, { method: "POST", body: JSON.stringify({ label, note }) });

export type WizardEvent =
  | { type: "text"; delta: string }
  | ({ type: "activity" } & Activity)
  | { type: "progress"; id: string; stage: string; message: string; done: number; total: number }
  | ({ type: "card" } & Card)
  | { type: "model"; model_id: string; title: string }
  | { type: "complete"; model_id: string }
  | { type: "done"; model_id: string | null }
  | { type: "error"; message: string };

/** POST a message and dispatch each streamed event; resolves when the turn ends. */
export async function streamWizard(sessionId: string, text: string, kind: "message" | "event", onEvent: (e: WizardEvent) => void, signal?: AbortSignal): Promise<void> {
  const token = await getAuthToken();
  const scope = getScopeUserId();
  const res = await fetch(`${API_BASE}${MW}/sessions/${sessionId}/messages`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...(scope ? { [SCOPE_HEADER]: scope } : {}),
    },
    body: JSON.stringify({ text, kind }),
    signal,
  });
  if (!res.ok || !res.body) {
    const detail = await res.json().then((b) => b?.detail as string | undefined).catch(() => undefined);
    throw new Error(detail || `The wizard is unavailable (${res.status})`);
  }
  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const frames = buffer.split("\n\n");
    buffer = frames.pop() ?? "";
    for (const frame of frames) {
      const line = frame.trim();
      if (!line.startsWith("data:")) continue;
      try { onEvent(JSON.parse(line.slice(5).trim()) as WizardEvent); } catch { /* partial frame */ }
    }
  }
}

/** Apply one streamed event to the assistant entry being built (pure; used by the chat and tests). */
export function applyEvent(parts: AssistantPart[], e: WizardEvent): AssistantPart[] {
  if (e.type === "text") {
    const last = parts[parts.length - 1];
    if (last?.type === "text") return [...parts.slice(0, -1), { ...last, text: last.text + e.delta }];
    return [...parts, { type: "text", text: e.delta }];
  }
  if (e.type === "activity") {
    const activity: Activity = { id: e.id, tool: e.tool, label: e.label, status: e.status, error: e.error };
    const i = parts.findIndex((p) => p.type === "activity" && p.id === e.id);
    if (i < 0) return [...parts, { type: "activity", ...activity }];
    return parts.map((p, j) => (j === i ? { ...(p as Activity & { type: "activity" }), ...activity, progress: undefined } : p));
  }
  if (e.type === "progress") {
    return parts.map((p) => (p.type === "activity" && p.id === e.id ? { ...p, progress: e.total > 1 ? `${e.message}` : e.message } : p));
  }
  if (e.type === "card") {
    return [...parts, { type: "card", id: e.id, kind: e.kind, props: e.props }];
  }
  return parts;
}

export type { Item, Prediction };
