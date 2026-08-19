// The whole Stash integration, server-side: write a turn with the customer's
// org id, read back with the same org id.
const BASE = process.env.STASH_BASE_URL ?? "http://localhost:3456";

function headers() {
  return {
    Authorization: `Bearer ${process.env.STASH_API_KEY}`,
    "Content-Type": "application/json",
  };
}

export async function read(org: string, script: string): Promise<string> {
  const res = await fetch(`${BASE}/api/v1/me/vfs`, {
    method: "POST",
    headers: headers(),
    body: JSON.stringify({ script, org_id: org }),
    cache: "no-store",
  });
  if (!res.ok) throw new Error(`stash read failed: ${res.status} ${await res.text()}`);
  return (await res.json()).stdout as string;
}

export async function record(
  org: string,
  orgName: string,
  session: string,
  events: [string, string][],
): Promise<void> {
  const res = await fetch(`${BASE}/api/v1/me/sessions/events/batch`, {
    method: "POST",
    headers: headers(),
    body: JSON.stringify({
      events: events.map(([event_type, content]) => ({
        agent_name: "travel-planner",
        event_type,
        content,
        session_id: session,
        org_id: org,
        org_name: orgName,
      })),
    }),
  });
  if (!res.ok) throw new Error(`stash write failed: ${res.status} ${await res.text()}`);
}

export async function listOrgs(): Promise<{ id: string; external_id: string; name: string; session_count: number }[]> {
  const res = await fetch(`${BASE}/api/v1/me/orgs`, { headers: headers(), cache: "no-store" });
  if (!res.ok) throw new Error(`stash orgs failed: ${res.status}`);
  return (await res.json()).orgs;
}

// Everything this customer may know: the shared wiki, and their own notepad.
// One root at a time — the VFS shell fails a whole command on a path that
// matches nothing.
export async function context(org: string): Promise<string> {
  const parts: string[] = [];
  for (const root of ["/memory", "/files/notepad"]) {
    if ((await read(org, `ls ${root}`)).trim()) parts.push(await read(org, `cat ${root}/*`));
  }
  return parts.join("\n\n");
}
