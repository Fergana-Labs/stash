// The whole Stash integration, server-side: write a turn with the customer's
// tenant id, read back with the same tenant id.
const BASE = process.env.STASH_BASE_URL ?? "http://localhost:3456";

export type Turn = { role: "user" | "assistant"; content: string };
export type Conversation = { id: string; title: string };

function headers() {
  const key = process.env.STASH_API_KEY;
  // Without this the header goes out as "Bearer undefined" and every call
  // comes back 401, which reads like a bad key rather than a missing one.
  if (!key)
    throw new Error("STASH_API_KEY is not set — put it in .env.local");
  return { Authorization: `Bearer ${key}`, "Content-Type": "application/json" };
}

export type ScriptResult = { stdout: string; stderr: string; exitCode: number };

/**
 * Run one read-only shell command against this traveller's view of Stash.
 * A non-zero exit is a normal shell result — grep exits 1 when it finds
 * nothing — so it comes back in the result rather than as a thrown error.
 * Only an unreachable or refusing backend throws.
 */
export async function runScript(tenant: string, script: string): Promise<ScriptResult> {
  const res = await fetch(`${BASE}/api/v1/me/vfs`, {
    method: "POST",
    headers: headers(),
    body: JSON.stringify({ script, tenant_id: tenant }),
    cache: "no-store",
  });
  if (!res.ok)
    throw new Error(`stash read failed: ${res.status} ${await res.text()}`);
  const body = await res.json();
  return {
    stdout: (body.stdout ?? "") as string,
    stderr: (body.stderr ?? "") as string,
    exitCode: (body.exit_code ?? 0) as number,
  };
}

export async function read(tenant: string, script: string): Promise<string> {
  return (await runScript(tenant, script)).stdout;
}

export async function record(
  tenant: string,
  tenantName: string,
  session: string,
  events: [string, string][],
): Promise<void> {
  // Events uploaded without a time all land on the instant the batch arrived,
  // and a transcript of simultaneous events comes back in id order — which put
  // the answer above the question. Stamp them in the order they were said.
  const spoken = Date.now();
  const res = await fetch(`${BASE}/api/v1/me/sessions/events/batch`, {
    method: "POST",
    headers: headers(),
    body: JSON.stringify({
      events: events.map(([event_type, content], index) => ({
        agent_name: "travel-planner",
        event_type,
        content,
        created_at: new Date(spoken + index).toISOString(),
        session_id: session,
        tenant_id: tenant,
        tenant_name: tenantName,
      })),
    }),
  });
  if (!res.ok)
    throw new Error(`stash write failed: ${res.status} ${await res.text()}`);
}

/**
 * The chat history in the sidebar, read back through the customer's own tenant
 * view — so the list can only ever hold conversations that customer had.
 * Newest first. Stash titles a session from its opening message.
 */
export async function listConversations(tenant: string): Promise<Conversation[]> {
  const index = await read(tenant, "cat /sessions/_index.jsonl");
  const sessions = index
    .split("\n")
    .filter((line) => line.trim())
    .map((line) => JSON.parse(line));
  sessions.sort((a, b) => b.updated_at.localeCompare(a.updated_at));
  return sessions.map((s) => ({ id: s.session_id, title: s.title }));
}

/**
 * One conversation's turns. A session's directory is named after its title
 * rather than its id, so the id is looked up where it is written down —
 * metadata.json — and the transcript read from alongside it.
 */
export async function readConversation(tenant: string, sessionId: string): Promise<Turn[]> {
  const pattern = quote(`"session_id": "${sessionId}"`);
  const hits = await read(tenant, `grep -r ${pattern} /sessions`);
  const hit = hits.split("\n").find((line) => line.includes("/metadata.json:"));
  if (!hit) throw new Error(`no session ${sessionId} in this tenant's view`);
  const directory = hit.slice(0, hit.indexOf("/metadata.json:"));
  return parseTranscript(await read(tenant, `cat ${quote(`${directory}/transcript.md`)}`));
}

// transcript.md is a run of "## <role> - <iso timestamp>" headings with the
// turn's text underneath. Roles other than user/assistant are tool activity,
// which this app never writes.
function parseTranscript(markdown: string): Turn[] {
  const turns: Turn[] = [];
  for (const block of markdown.split(/^## /m).slice(1)) {
    const breakAt = block.indexOf("\n");
    if (breakAt === -1) continue;
    const role = block.slice(0, breakAt).split(" ")[0];
    if (role !== "user" && role !== "assistant") continue;
    turns.push({ role, content: block.slice(breakAt + 1).trim() });
  }
  return turns;
}

// A session directory is named after the traveller's opening question, so the
// path holds whatever they typed — apostrophes included.
function quote(value: string): string {
  return `'${value.replace(/'/g, `'\\''`)}'`;
}

export type SessionRow = { id: string; sessionId: string; title: string };

/** Every session in this traveller's view, with the row id the delete route takes. */
export async function listSessionRows(tenant: string): Promise<SessionRow[]> {
  const index = await read(tenant, "cat /sessions/_index.jsonl");
  return index
    .split("\n")
    .filter((line) => line.trim())
    .map((line) => JSON.parse(line))
    .map((row) => ({ id: row.id, sessionId: row.session_id, title: row.title }));
}

/** Trash then purge — the purge route only accepts a session already in trash. */
export async function purgeSession(rowId: string): Promise<void> {
  for (const path of [`/api/v1/me/sessions/${rowId}`, `/api/v1/me/sessions/${rowId}/purge`]) {
    const res = await fetch(`${BASE}${path}`, { method: "DELETE", headers: headers() });
    if (!res.ok && res.status !== 404)
      throw new Error(`purge failed: ${res.status} ${await res.text()}`);
  }
}
