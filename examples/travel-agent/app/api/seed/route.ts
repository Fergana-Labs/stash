import { answer } from "@/lib/agent";
import { record } from "@/lib/stash";
import { travellerById } from "@/lib/travellers";

/**
 * The scenario worth showing, run by `npm run seed` rather than from the UI:
 * one traveller learns something about the world the hard way and mentions
 * something private about how they travel; a second traveller asks about a trip
 * of their own. After a curator run the first traveller's lesson reaches the
 * second, and the private preference does not.
 */
const SCRIPT: [string, string][] = [
  ["sam", "I need a Vietnam e-visa for a trip in 3 weeks. Is that enough time?"],
  [
    "sam",
    "Update: that e-visa took 19 working days, not the 3 the site claims. I nearly missed the flight. Never count on three days again.",
  ],
  ["sam", "Also, for future trips: I won't fly overnight, and I always want an aisle seat."],
  ["priya", "Six of us want to get from Berlin to Lisbon in May. What's the best way?"],
];

export async function POST() {
  try {
    const turns = [];
    for (const [tenant, question] of SCRIPT) {
      let reply = "";
      for await (const event of answer(tenant, [{ role: "user", content: question }]))
        if (event.type === "text") reply += event.delta;
      await record(tenant, travellerById(tenant).name, `${tenant}:seed`, [
        ["user_message", question],
        ["assistant_message", reply],
      ]);
      turns.push({ tenant, question, reply });
    }
    return Response.json({ turns });
  } catch (e) {
    console.error("[seed] failed:", e);
    return Response.json({ error: e instanceof Error ? e.message : String(e) }, { status: 500 });
  }
}
