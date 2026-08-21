import { record } from "@/lib/stash";

/**
 * Uploading transcripts, which is not the same mechanism as the agent reading
 * memory. Heavi and everyone like them do this from their backend, on their own
 * schedule — after the turn, in a batch, from a queue worker — so it is its own
 * endpoint here rather than something the answering path does on the way past.
 *
 * This is the only place a session id appears: it groups turns into one
 * transcript. It is not a security boundary — tenant_id is.
 */
export async function POST(request: Request) {
  const { tenant, tenantName, session, question, reply } = await request.json();
  try {
    await record(tenant, tenantName, session, [
      ["user_message", question],
      ["assistant_message", reply],
    ]);
    return Response.json({ recorded: true });
  } catch (e) {
    console.error("[record] upload failed:", e);
    return Response.json({ error: "This chat was not saved." }, { status: 500 });
  }
}
