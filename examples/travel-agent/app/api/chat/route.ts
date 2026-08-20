import { answer } from "@/lib/agent";

// The agent answering. Reads that agency's memory with nothing but an org id;
// recording the turn is a separate mechanism (see api/record).
export async function POST(request: Request) {
  try {
    const { org, question } = await request.json();
    return Response.json({ reply: await answer(org, question) });
  } catch (e) {
    return Response.json({ error: e instanceof Error ? e.message : String(e) }, { status: 500 });
  }
}
