import { API_BASE, apiFetch, getAuthToken } from "@/lib/api";
import { SCOPE_HEADER, getScopeUserId } from "@/lib/scope-store";

/** Client for /api/v1/evals (backend/routers/evals.py): examples marked good or bad in,
 * one endpoint out that scores an agent's trace and output. */
const T = "/api/v1/evals";

export type EvalLabel = "good" | "bad";
export interface EvalTrait { name: string; good: string; bad: string }
export interface EvalBuild {
  stage: "queued" | "traits" | "checking" | "done" | "failed";
  done?: number;
  total?: number;
  error?: string | null;
  summary?: string;
  metrics?: { checked: number; agreement: number | null; good_above_bad: number | null };
}
export interface Eval {
  id: string;
  name: string;
  instructions: string;
  traits: EvalTrait[];
  build: EvalBuild | null;
  ready: boolean;
  examples: { good: number; bad: number };
  calls: number;
  endpoint: string;
  created_at: string;
  updated_at: string;
}
export interface EvalFile { key: string; name: string; content_type: string }
export interface EvalItem { name: string; trace: { role: string; content: string; tool_name?: string }[]; text: string; files: EvalFile[] }
export interface EvalExample { id: string; item: EvalItem; label: EvalLabel; note: string; source: string; created_at: string }
export interface EvalGrade { trait: string; score: number; why: string }
export interface EvalCall {
  id: string;
  input: EvalItem;
  score: number;
  traits: EvalGrade[];
  explanation: string;
  fixes: { issue: string; fix: string }[];
  caller: string;
  created_at: string;
  label: EvalLabel | null;
  note: string;
}

export const evalCreate = (name: string, instructions = "") =>
  apiFetch<Eval>(T, { method: "POST", body: JSON.stringify({ name, instructions }) });
export const evalGet = (id: string) => apiFetch<Eval>(`${T}/${id}`);
export const evalList = () => apiFetch<{ evals: Eval[] }>(T).then((r) => r.evals);
export const evalBuild = (id: string) => apiFetch<Eval>(`${T}/${id}/build`, { method: "POST" });
export const evalExamples = (id: string) => apiFetch<{ examples: EvalExample[] }>(`${T}/${id}/examples`).then((r) => r.examples);
export const evalDeleteExample = (id: string, exampleId: string) => apiFetch<void>(`${T}/${id}/examples/${exampleId}`, { method: "DELETE" });
export const evalCalls = (id: string) => apiFetch<{ calls: EvalCall[] }>(`${T}/${id}/calls`).then((r) => r.calls);
export const evalLabelCall = (id: string, callId: string, label: EvalLabel | null, note = "") =>
  apiFetch(`${T}/${id}/calls/${callId}/label`, { method: "PUT", body: JSON.stringify({ label, note }) });
export const evalExampleFilePath = (id: string, exampleId: string, index: number) => `${T}/${id}/examples/${exampleId}/files/${index}`;
export const evalCallFilePath = (id: string, callId: string, index: number) => `${T}/${id}/calls/${callId}/files/${index}`;

/** Upload files as examples (one example each). Multipart, so it sets its own headers. */
export async function evalUploadExamples(id: string, label: EvalLabel, files: File[]): Promise<EvalExample[]> {
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
