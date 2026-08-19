import { context, record } from "@/lib/stash";

const MODEL = "claude-sonnet-4-6";
const SYSTEM = `You are a travel planner working for a travel agency.

Context comes from two places: general travel knowledge learned across many
agencies, and this agency's own notes about their travellers. Use both. Be
concrete — name airlines, airports, visa timelines, neighbourhoods. Three
sentences at most unless asked for an itinerary.

You do not know which other agencies exist and must never speculate about them.`;

export async function POST(request: Request) {
  try {
    return await chat(request);
  } catch (e) {
    return Response.json(
      { error: e instanceof Error ? e.message : String(e) },
      { status: 500 },
    );
  }
}

async function chat(request: Request) {
  const { org, orgName, session, question } = await request.json();
  const ctx = await context(org);

  const res = await fetch("https://api.anthropic.com/v1/messages", {
    method: "POST",
    headers: {
      "x-api-key": process.env.ANTHROPIC_API_KEY!,
      "anthropic-version": "2023-06-01",
      "content-type": "application/json",
    },
    body: JSON.stringify({
      model: MODEL,
      max_tokens: 400,
      system: SYSTEM,
      messages: [
        {
          role: "user",
          content: `What we know:\n${ctx || "(nothing yet)"}\n\n${question}`,
        },
      ],
    }),
  });
  if (!res.ok)
    return Response.json({ error: await res.text() }, { status: 502 });
  const body = await res.json();
  const reply = body.content
    .filter((b: { type: string }) => b.type === "text")
    .map((b: { text: string }) => b.text)
    .join("");

  await record(org, orgName, session, [
    ["user_message", question],
    ["assistant_message", reply],
  ]);
  return Response.json({ reply, contextChars: ctx.length });
}
