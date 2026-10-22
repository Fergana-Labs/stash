import { API_BASE, apiFetch, getAuthToken } from "@/lib/api";
import { SCOPE_HEADER, getScopeUserId } from "@/lib/scope-store";

/** Client for /api/v1/image-evals (backend/routers/image_evals.py). */
const T = "/api/v1/image-evals";

export type ImageEvalLabel = "liked" | "disliked";

export interface ImageEvalBuild {
  stage: "queued" | "brief" | "imitations" | "training" | "done" | "failed";
  done?: number;
  total?: number;
  imitations?: number;
  error?: string | null;
  /** Unix seconds when the build was queued. */
  started_at?: number;
}
export interface ImageEvalSummary {
  id: string;
  model_id: string | null;
  name: string;
  description: string;
  style_brief: string;
  build: ImageEvalBuild | null;
  trained: boolean;
  trained_at: string | null;
  heldout_accuracy: number | null;
  heldout_balanced_accuracy: number | null;
  heldout_method: string | null;
  liked: number | null;
  disliked: number | null;
  created_at: string;
  updated_at: string;
}
export interface ImageEvalListItem extends ImageEvalSummary { calls: number; examples: number }
export interface ImageEvalDetail extends ImageEvalSummary {
  examples: { liked: number; disliked: number; imitations: number };
  calls: number;
  needs_training: boolean;
}
export interface ImageEvalExample {
  id: string;
  label: ImageEvalLabel;
  source: "upload" | "call" | "imitation";
  call_id: string | null;
  filename: string;
  note: string;
  heldout_score: number | null;
  created_at: string;
}
export interface ImageEvalFix { issue: string; fix: string }
export interface ImageEvalComments { summary: string; fixes: ImageEvalFix[]; keep: string[] }
export interface ImageEvalCall {
  id: string;
  caller: string;
  task: string;
  score: number;
  comments: ImageEvalComments | null;
  created_at: string;
  feedback_label: ImageEvalLabel | null;
  feedback_note: string | null;
}

export const imageEvalList = () => apiFetch<{ classifiers: ImageEvalListItem[] }>(T).then((r) => r.classifiers);
export const imageEvalCreate = (name: string, description = "") =>
  apiFetch<ImageEvalSummary>(T, { method: "POST", body: JSON.stringify({ name, description }) });
export const imageEvalGet = (id: string) => apiFetch<ImageEvalDetail>(`${T}/${id}`);
/** The image eval behind a wizard-made eval; rejects (404) when the eval is another kind. */
export const imageEvalByModel = (modelId: string) => apiFetch<ImageEvalDetail>(`${T}/by-model/${modelId}`);
export const imageEvalDelete = (id: string) => apiFetch<void>(`${T}/${id}`, { method: "DELETE" });
export const imageEvalBuild = (id: string) => apiFetch<ImageEvalDetail>(`${T}/${id}/build`, { method: "POST" });
export const imageEvalTrain = (id: string) => apiFetch<ImageEvalDetail>(`${T}/${id}/train`, { method: "POST" });
export const imageEvalExamples = (id: string) =>
  apiFetch<{ examples: ImageEvalExample[] }>(`${T}/${id}/examples`).then((r) => r.examples);
export const imageEvalDeleteExample = (id: string, exampleId: string) =>
  apiFetch<void>(`${T}/${id}/examples/${exampleId}`, { method: "DELETE" });
export const imageEvalCalls = (id: string) =>
  apiFetch<{ calls: ImageEvalCall[] }>(`${T}/${id}/calls`).then((r) => r.calls);
export const imageEvalLabelCall = (id: string, callId: string, label: ImageEvalLabel | null, note = "") =>
  apiFetch<{ call_id: string }>(`${T}/${id}/calls/${callId}/label`, { method: "PUT", body: JSON.stringify({ label, note }) });
export const imageEvalExampleImagePath = (id: string, exampleId: string) => `${T}/${id}/examples/${exampleId}/image`;
export const imageEvalCallImagePath = (id: string, callId: string) => `${T}/${id}/calls/${callId}/image`;

/** Upload images as examples. Multipart, so it sets its own headers instead of apiFetch's JSON ones. */
export async function imageEvalUploadExamples(id: string, label: ImageEvalLabel, files: File[]): Promise<ImageEvalExample[]> {
  const form = new FormData();
  form.append("label", label);
  for (const file of files) form.append("files", file);
  const headers: Record<string, string> = {};
  const token = await getAuthToken();
  if (token) headers["Authorization"] = `Bearer ${token}`;
  const scope = getScopeUserId();
  if (scope) headers[SCOPE_HEADER] = scope;
  const resp = await fetch(`${API_BASE}${T}/${id}/examples`, { method: "POST", headers, body: form });
  if (!resp.ok) throw new Error(await resp.json().then((d) => d.detail).catch(() => resp.statusText));
  return (await resp.json()).examples;
}
