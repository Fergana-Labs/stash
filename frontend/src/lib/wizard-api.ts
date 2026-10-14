import { API_BASE, apiFetch, getAuthToken } from "@/lib/api";
import { getScopeUserId, SCOPE_HEADER } from "@/lib/scope-store";
import type { Evaluation, Gate, Item, Prediction, RubricQuestion } from "@/lib/intuition-api";

/** Client for /api/v1/model-wizard (backend/routers/model_wizard.py). */
const MW = "/api/v1/model-wizard";

export type CardKind = "choices" | "uploader" | "labeler" | "criteria" | "report" | "playground" | "review" | "robustness" | "examples";
export interface Card { id: string; kind: CardKind; props: Record<string, unknown> }
export interface Activity { id: string; tool: string; label: string; status: "running" | "done" | "error"; error?: string | null; progress?: string }
export type AssistantPart = ({ type: "text"; text: string }) | ({ type: "card" } & Card) | ({ type: "activity" } & Activity);
export type TranscriptEntry =
  | { role: "user"; kind: "message" | "event"; text: string }
  | { role: "assistant"; parts: AssistantPart[] };

export interface WizardSession {
  id: string; model_id: string | null; title: string; created_at: string; updated_at: string;
  transcript?: TranscriptEntry[]; model_name?: string | null;
}

export interface LeaderboardRow { name: string; detail: string; n: number; accuracy: number | null; log_loss: number | null; ece: number | null; shipping?: boolean }
export interface TrainingReport {
  version: number;
  counts: { train: number; held_out: number; labels: Record<string, number> };
  holdout: Pick<Evaluation, "n" | "accuracy" | "log_loss" | "ece" | "confusion" | "rows"> & { accuracy_interval: [number, number] | null; reliability: NonNullable<Evaluation["reliability"]> };
  train_accuracy: number | null;
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
export const wzDelete = (id: string) => apiFetch<void>(`${MW}/sessions/${id}`, { method: "DELETE" });
export const wzTrain = (modelId: string) => post<TrainingReport>(`${MW}/models/${modelId}/train`);
export const wzReport = (modelId: string) => apiFetch<{ report: TrainingReport | null }>(`${MW}/models/${modelId}/report`);
export const wzDiscover = (modelId: string, body: { count?: number; guidance?: string } = {}) => post<Discovery>(`${MW}/models/${modelId}/discover`, body);
export const wzHarden = (modelId: string, target_label?: string) => post<HardenResult>(`${MW}/models/${modelId}/harden`, { target_label: target_label ?? null });

export type WizardEvent =
  | { type: "text"; delta: string }
  | ({ type: "activity" } & Activity)
  | { type: "progress"; id: string; stage: string; message: string; done: number; total: number }
  | ({ type: "card" } & Card)
  | { type: "model"; model_id: string; title: string }
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
