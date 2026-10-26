import { API_BASE, apiFetch, getAuthToken } from "@/lib/api";
import { SCOPE_HEADER, getScopeUserId } from "@/lib/scope-store";

/** Client for /api/v1/evals (backend/routers/evals.py): examples marked good or bad in,
 * one endpoint out that scores an agent's trace and output. Each eval has a channel where
 * people drop examples and say what they think, and a rubric that keeps up with them. */
const T = "/api/v1/evals";

export type EvalLabel = "good" | "bad";
/** by: "person" marks a trait the person wrote or changed; revisions keep it as written. */
export interface EvalTrait { name: string; good: string; bad: string; basis?: string; by?: "person" }
export interface EvalTally { n: number; right: number; agreement: number | null; good_above_bad: number | null }
export interface EvalBuild {
  stage: "queued" | "starting" | "traits" | "checking" | "revising" | "done" | "failed";
  done?: number;
  total?: number;
  error?: string | null;
  summary?: string;
  metrics?: { checked: number; agreement: number | null; good_above_bad: number | null; held_out?: EvalTally };
}
export const EVAL_BUILDING: EvalBuild["stage"][] = ["queued", "starting", "traits", "checking", "revising"];
export interface Eval {
  id: string;
  name: string;
  instructions: string;
  traits: EvalTrait[];
  build: EvalBuild | null;
  ready: boolean;
  version: number | null;
  examples: { good: number; bad: number };
  unlabeled: number;
  calls: number;
  agent_busy: boolean;
  endpoint: string;
  created_at: string;
  updated_at: string;
}
export interface EvalFile { key: string; name: string; content_type: string }
export interface EvalItem { name: string; trace: { role: string; content: string; tool_name?: string }[]; text: string; files: EvalFile[] }
export interface EvalExample { id: string; item: EvalItem; label: EvalLabel | null; note: string; source: string; split: "train" | "eval"; message_id: string | null; created_at: string }
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

export interface EvalAttachment { example_id: string; name: string; content_type: string; label: EvalLabel | null; note: string; held_out: boolean }
export interface EvalChange { kind: string; trait: string; why: string }
export interface EvalManipulation { n: number; resisted: number; worst: { score: number; base: number | null; claim: string } }
export interface EvalMetrics { fit: EvalTally; check: EvalTally; manipulation?: EvalManipulation }
export interface EvalMessage {
  id: string;
  thread_id: string | null;
  author: "user" | "agent";
  kind: "message" | "rubric";
  text: string;
  data: {
    choices?: string[];
    about?: string;
    uploading?: boolean;
    version?: number;
    changes?: EvalChange[];
    metrics?: EvalMetrics | null;
    before?: EvalMetrics | null;
  };
  attachments: EvalAttachment[];
  about: EvalAttachment | null;
  created_at: string;
}
export interface EvalRubricVersion {
  id: string;
  number: number;
  traits: EvalTrait[];
  instructions: string;
  source: "written" | "revised" | "edited";
  changes: EvalChange[];
  metrics: EvalMetrics | null;
  created_at: string;
}

export const evalCreate = (name: string, instructions = "") =>
  apiFetch<Eval>(T, { method: "POST", body: JSON.stringify({ name, instructions }) });
export const evalGet = (id: string) => apiFetch<Eval>(`${T}/${id}`);
export const evalList = () => apiFetch<{ evals: Eval[] }>(T).then((r) => r.evals);
export const evalBuild = (id: string, fresh = false) => apiFetch<Eval>(`${T}/${id}/build${fresh ? "?fresh=true" : ""}`, { method: "POST" });
export const evalRename = (id: string, name: string) => apiFetch<Eval>(`${T}/${id}`, { method: "PATCH", body: JSON.stringify({ name }) });
export const evalEditExample = (id: string, exampleId: string, label: EvalLabel | null, note?: string) =>
  apiFetch<EvalExample>(`${T}/${id}/examples/${exampleId}`, { method: "PATCH", body: JSON.stringify(note === undefined ? { label } : { label, note }) });
export const evalRubric = (id: string) => apiFetch<{ versions: EvalRubricVersion[] }>(`${T}/${id}/rubric`).then((r) => r.versions);
/** base: the version the edit was made on; the server refuses it if that's no longer current. */
export const evalEditRubric = (id: string, traits: EvalTrait[], base: number) =>
  apiFetch<{ versions: EvalRubricVersion[] }>(`${T}/${id}/rubric`, {
    method: "PUT",
    body: JSON.stringify({ base, traits: traits.map(({ name, good, bad, basis }) => ({ name, good, bad, basis: basis ?? "" })) }),
  }).then((r) => r.versions);
export const evalMessages = (id: string) => apiFetch<{ messages: EvalMessage[]; busy: boolean }>(`${T}/${id}/messages`);

/** Files per request when posting to the channel; bigger drops go up in parts. */
const POST_FILES = 8;

/** Post to the eval's channel. A drop bigger than one request is posted with its first
 * files, the rest follow in order, and the agent reads it once the last part is up. */
export async function evalPost(id: string, { text = "", threadId, files = [], onProgress }: { text?: string; threadId?: string; files?: File[]; onProgress?: (sent: number) => void }) {
  const form = (part: File[], more: boolean, first: boolean) => {
    const body = new FormData();
    if (first) {
      body.append("text", text);
      if (threadId) body.append("thread_id", threadId);
    }
    body.append("more", more ? "true" : "false");
    for (const file of part) body.append("files", file);
    return body;
  };
  const parts = Array.from({ length: Math.max(1, Math.ceil(files.length / POST_FILES)) }, (_, i) => files.slice(i * POST_FILES, (i + 1) * POST_FILES));
  type Posted = { message: EvalMessage; skipped: { name: string; error: string }[] };
  const first = await apiFetch<Posted>(`${T}/${id}/messages`, { method: "POST", body: form(parts[0], parts.length > 1, true) });
  const skipped = [...first.skipped];
  let message = first.message;
  onProgress?.(parts[0].length);
  try {
    for (let i = 1; i < parts.length; i++) {
      const next = await apiFetch<Posted>(`${T}/${id}/messages/${message.id}/files`, { method: "POST", body: form(parts[i], i < parts.length - 1, false) });
      skipped.push(...next.skipped);
      message = next.message;
      onProgress?.(Math.min(files.length, (i + 1) * POST_FILES));
    }
  } catch (error) {
    // Hand the agent what did arrive rather than leave the message waiting for parts.
    await apiFetch(`${T}/${id}/messages/${message.id}/files`, { method: "POST", body: form([], false, false) }).catch(() => {});
    throw error;
  }
  return { message, skipped };
}
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
