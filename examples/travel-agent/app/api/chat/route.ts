import { answer, type AgentEvent } from "@/lib/agent";

/**
 * The agent answering, as a stream of events: assistant text, and every read it
 * makes against Stash. One JSON object per line — the browser draws the reads
 * as they happen, which is the point of showing them at all.
 *
 * A configuration problem here — no Stash key, no model key — is the operator's
 * to fix, so it goes to the server log in full and the browser is told only
 * that the answer failed.
 */
export async function POST(request: Request) {
  const { tenant, messages } = await request.json();
  try {
    const events = answer(tenant, messages);
    // The first event is awaited here so a bad key fails as a 500 rather than
    // as an empty stream the browser has already started rendering.
    const first = await events.next();
    return new Response(
      new ReadableStream({
        async start(controller) {
          const send = (event: AgentEvent) =>
            controller.enqueue(new TextEncoder().encode(`${JSON.stringify(event)}\n`));
          if (!first.done) send(first.value);
          for await (const event of events) send(event);
          controller.close();
        },
      }),
      { headers: { "Content-Type": "application/x-ndjson; charset=utf-8" } },
    );
  } catch (e) {
    console.error("[chat] answering failed:", e);
    return Response.json({ error: "Atlas could not answer just now." }, { status: 500 });
  }
}
