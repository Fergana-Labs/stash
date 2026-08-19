import { read } from "@/lib/stash";

// A customer's own transcripts, read through their own org view — the same
// call their agent makes, so what this page shows is what they can see.
export async function GET(request: Request) {
  const org = new URL(request.url).searchParams.get("org");
  if (!org) return Response.json({ error: "org required" }, { status: 400 });
  try {
    const listing = await read(org, "ls /sessions");
    const names = listing
      .split("\n")
      .map((l) => l.trim())
      .filter((l) => l && l !== "_index.jsonl");
    const sessions = [];
    for (const name of names) {
      sessions.push({
        name,
        transcript: await read(org, `cat "/sessions/${name}/transcript.md"`),
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
