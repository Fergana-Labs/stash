import { read } from "@/lib/stash";

// A customer's own transcripts, read through their own tenant view — the same
// call their agent makes, so what this page shows is what they can see.
export async function GET(request: Request) {
  const tenant = new URL(request.url).searchParams.get("tenant");
  if (!tenant) return Response.json({ error: "tenant required" }, { status: 400 });
  try {
    const listing = await read(tenant, "ls /sessions");
    const names = listing
      .split("\n")
      .map((l) => l.trim())
      .filter((l) => l && l !== "_index.jsonl");
    const sessions = [];
    for (const name of names) {
      sessions.push({
        name,
        transcript: await read(tenant, `cat "/sessions/${name}/transcript.md"`),
      });
    }
    return Response.json({ sessions });
  } catch (e) {
    return Response.json(
      { error: e instanceof Error ? e.message : String(e) },
      { status: 500 },
    );
  }
}
