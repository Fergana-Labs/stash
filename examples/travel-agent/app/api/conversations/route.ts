import { listConversations, readConversation } from "@/lib/stash";

// The sidebar's chat history, and any one conversation in it, read through the
// customer's own tenant view — the same call their agent makes, so the list
// holds what they can see and nothing else.
export async function GET(request: Request) {
  const params = new URL(request.url).searchParams;
  const tenant = params.get("tenant");
  const session = params.get("session");
  if (!tenant) return Response.json({ error: "tenant required" }, { status: 400 });
  try {
    if (session) return Response.json({ turns: await readConversation(tenant, session) });
    return Response.json({ conversations: await listConversations(tenant) });
  } catch (e) {
    console.error("[conversations] read failed:", e);
    return Response.json({ error: "Chat history is unavailable." }, { status: 500 });
  }
}
