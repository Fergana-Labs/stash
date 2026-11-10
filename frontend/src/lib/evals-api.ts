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
  /** Rubric changes wait for approval instead of being saved; how many are waiting now. */
  review_required: boolean;
  open_changes: number;
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
/** added_by: the user whose request added it; added_via: "web" (the app) or "api" (an API key,
 * how agents add examples), "" before this was recorded; caller and session_id: what an agent
 * said about itself when it added the example. */
export interface EvalExample {
  id: string; item: EvalItem; label: EvalLabel | null; note: string; source: string; split: "train" | "eval"; message_id: string | null; created_at: string;
  added_by: string | null; added_via: "web" | "api" | ""; caller: string; session_id: string | null;
}
/** session: the Stash session the example was added from, when Stash tracked it. call: the scored
 * call it came from, when someone labeled one. */
export interface EvalExampleDetail extends EvalExample {
  added_by_name: string | null;
  session: { session_id: string; title: string | null; agent_name: string } | null;
  call: { id: string; caller: string; created_at: string } | null;
}
/** A trait's grade. When a call graded a change rather than the whole output, a trait the
 * change didn't touch has no score, and touched ones say whether the change helped. */
export interface EvalGrade { trait: string; score: number | null; why: string; touched?: boolean; effect?: "better" | "same" | "worse" | null }
export interface EvalCall {
  id: string;
  input: EvalItem;
  mode?: "change";
  score: number;
  traits: EvalGrade[];
  explanation: string;
  fixes: { issue: string; fix: string }[];
  caller: string;
  /** The rubric version that scored this call. */
  rubric_version: number | null;
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
    /** The proposed rubric change this message reports. */
    proposal?: number;
    choices?: string[];
    about?: string;
    uploading?: boolean;
    via?: string;
    version?: number;
    changes?: EvalChange[];
    metrics?: EvalMetrics | null;
    before?: EvalMetrics | null;
  };
  attachments: EvalAttachment[];
  about: EvalAttachment | null;
  /** The person's message the agent hasn't read yet. */
  unread?: boolean;
  created_at: string;
}
export interface EvalRubricVersion {
  id: string;
  number: number;
  traits: EvalTrait[];
  instructions: string;
  /** How trait grades become one score: their mean, or the lowest (one failing trait fails the work). */
  scoring: "mean" | "lowest";
  source: "written" | "revised" | "edited";
  changes: EvalChange[];
  metrics: EvalMetrics | null;
  quality: EvalQuality | null;
  /** The person who edited the rubric directly. */
  created_by: string | null;
  /** The approved change this version came from. */
  approved: { proposal: number; by: string | null; at: string; note: string } | null;
  /** The agent calls this version scored. */
  used: { calls: number; first: string; last: string; callers: string[] } | null;
  created_at: string;
}
/** A rubric's quality, 0-100: the mean of its parts (each 0-1). */
export interface EvalQuality { score: number; parts: { agreement?: number; ranking?: number; manipulation?: number } }
/** low: the trait a regraded agent call scores lowest on under the proposed rubric, and why. */
export interface EvalFlip { id: string; before: number; after: number; low?: { trait: string; why: string } | null }
/** What a proposed rubric change was measured to do, against the version it would replace. */
export interface EvalChecks {
  before: { fit: EvalTally; check: EvalTally } | null;
  after: { fit: EvalTally; check: EvalTally } | null;
  /** Labeled examples whose verdict the change sets right, and the ones it sets wrong. */
  fixed: EvalFlip[];
  broke: EvalFlip[];
  /** Examples added since the version the change was proposed on. */
  evidence: string[];
  /** Recent agent calls graded again with the proposed rubric. */
  calls: { n: number; mean_before: number; mean_after: number; pass_before: number; pass_after: number; changed: EvalFlip[]; calls: EvalFlip[] } | null;
  /** What kind of agent output the proposed rubric treats differently from the one in use, in one sentence. */
  summary?: string | null;
  manipulation: EvalManipulation | null;
  short: { graded: number; of: number } | null;
}
export interface EvalSnippet { id: string; name: string; asked: string; text: string; files: { name: string; content_type: string }[] }
export interface EvalChangeExample extends EvalSnippet {
  label: EvalLabel | null; note: string; held_out: boolean; created_at: string;
  added_by_name: string | null; added_via: "web" | "api" | ""; caller: string;
}
export interface EvalChangeCall extends EvalSnippet { caller: string; created_at: string }
/** A comment on a proposed change; trait names the rubric trait it is about, "" for the whole change. */
export interface EvalComment { id: string; author: string | null; trait: string; body: string; created_at: string }
/** A proposed change to the rubric: what it would become, on which version, and its checks. */
export interface EvalProposal {
  id: string;
  number: number;
  /** What the change is called, as a branch is; "" when it has no name of its own. */
  name: string;
  base: number;
  status: "open" | "approved" | "rejected";
  source: EvalRubricVersion["source"];
  traits: EvalTrait[];
  scoring: EvalRubricVersion["scoring"];
  instructions: string;
  changes: EvalChange[];
  /** null while the checks are still running. */
  checks: EvalChecks | null;
  passed: boolean | null;
  quality: { before: EvalQuality | null; after: EvalQuality | null };
  /** The rubric it would replace. */
  before: { number: number; traits: EvalTrait[]; scoring: EvalRubricVersion["scoring"]; instructions: string } | null;
  /** The person who edited the rubric to propose it; null when the wizard drafted it. */
  proposed_by: string | null;
  /** Who the change was opened by: that person, or the eval's owner when the wizard drafted it
   * from their examples. */
  opened_by: string | null;
  decided_by: string | null;
  decided_at: string | null;
  note: string;
  /** The rubric version an approval saved. */
  version: number | null;
  /** Open, but made on a version that is no longer current: it can't be approved. */
  stale: boolean;
  examples: Record<string, EvalChangeExample>;
  calls: Record<string, EvalChangeCall>;
  comments: EvalComment[];
  created_at: string;
}
export interface EvalChanges { review_required: boolean; proposals: EvalProposal[] }

export const evalCreate = (name: string, instructions = "") =>
  apiFetch<Eval>(T, { method: "POST", body: JSON.stringify({ name, instructions }) });
export const evalGet = (id: string) => apiFetch<Eval>(`${T}/${id}`);
export const evalList = () => apiFetch<{ evals: Eval[] }>(T).then((r) => r.evals);
export const evalBuild = (id: string, fresh = false) => apiFetch<Eval>(`${T}/${id}/build${fresh ? "?fresh=true" : ""}`, { method: "POST" });
export const evalRename = (id: string, name: string) => apiFetch<Eval>(`${T}/${id}`, { method: "PATCH", body: JSON.stringify({ name }) });
export const evalExample = (id: string, exampleId: string) => apiFetch<EvalExampleDetail>(`${T}/${id}/examples/${exampleId}`);
export const evalEditExample = (id: string, exampleId: string, label: EvalLabel | null, note?: string) =>
  apiFetch<EvalExample>(`${T}/${id}/examples/${exampleId}`, { method: "PATCH", body: JSON.stringify(note === undefined ? { label } : { label, note }) });
export const evalRubric = (id: string) => apiFetch<{ versions: EvalRubricVersion[] }>(`${T}/${id}/rubric`).then((r) => r.versions);
/** base: the version the edit was made on; the server refuses it if that's no longer current. */
export const evalEditRubric = (id: string, traits: EvalTrait[], base: number) =>
  apiFetch<{ versions: EvalRubricVersion[] }>(`${T}/${id}/rubric`, {
    method: "PUT",
    body: JSON.stringify({ base, traits: traits.map(({ name, good, bad, basis }) => ({ name, good, bad, basis: basis ?? "" })) }),
  }).then((r) => r.versions);
export const evalChanges = (id: string) => apiFetch<EvalChanges>(`${T}/${id}/changes`);
export const evalSetReview = (id: string, required: boolean) =>
  apiFetch<EvalChanges>(`${T}/${id}/review`, { method: "PUT", body: JSON.stringify({ required }) });
export const evalDecide = (id: string, proposalId: string, decision: "approve" | "reject", note: string) =>
  apiFetch<EvalChanges>(`${T}/${id}/changes/${proposalId}/${decision}`, { method: "POST", body: JSON.stringify({ note }) });
export const evalComment = (id: string, proposalId: string, body: string, trait = "") =>
  apiFetch<EvalChanges>(`${T}/${id}/changes/${proposalId}/comments`, { method: "POST", body: JSON.stringify({ body, trait }) });
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
