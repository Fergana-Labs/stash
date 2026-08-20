import { context } from "@/lib/stash";

const MODEL = "claude-sonnet-4-6";

const SYSTEM = `You are a travel planner working for a travel agency.

Context comes from two places: general travel knowledge learned across many
agencies, and this agency's own notes about their travellers. Use both. Be
concrete — name airlines, airports, visa timelines, neighbourhoods. Three
sentences at most unless asked for an itinerary.

You do not know which other agencies exist and must never speculate about them.`;

/**
 * The agent's own tool call: read what this agency is allowed to know, then
 * answer. `org` is the only thing Stash needs — it is the isolation boundary.
 * There is no session here, because reading memory has nothing to do with
 * which conversation you are in.
 */
export async function answer(org: string, question: string): Promise<string> {
  return claude(await context(org), question);
}

async function claude(ctx: string, question: string): Promise<string> {
  const key = process.env.ANTHROPIC_API_KEY;
  if (!key) throw new Error("ANTHROPIC_API_KEY is not set — put it in .env.local");
  const res = await fetch("https://api.anthropic.com/v1/messages", {
    method: "POST",
    headers: {
      "x-api-key": key,
      "anthropic-version": "2023-06-01",
      "content-type": "application/json",
    },
    body: JSON.stringify({
      model: MODEL,
      max_tokens: 400,
      system: SYSTEM,
      messages: [
        { role: "user", content: `What we know:\n${ctx || "(nothing yet)"}\n\n${question}` },
      ],
    }),
  });
  if (!res.ok) throw new Error(`anthropic ${res.status}: ${await res.text()}`);
  const body = await res.json();
  return body.content
    .filter((b: { type: string }) => b.type === "text")
    .map((b: { text: string }) => b.text)
    .join("");
}
