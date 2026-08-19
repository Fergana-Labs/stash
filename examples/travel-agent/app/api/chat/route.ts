import { answer } from "@/lib/agent";

export async function POST(request: Request) {
  try {
    const { org, orgName, session, question } = await request.json();
    return Response.json({ reply: await answer(org, orgName, session, question) });
  } catch (e) {
    return Response.json({ error: e instanceof Error ? e.message : String(e) }, { status: 500 });
  }
}
