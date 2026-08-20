import { answer } from "@/lib/agent";
import { record } from "@/lib/stash";

// The scenario worth showing: one agency learns something about the world the
// hard way and records something private about a traveller; a second agency
// asks about its own business. After a curator run the first agency's lesson
// reaches the second, and the private note does not.
const SCRIPT: [string, string, string][] = [
  ["wanderly", "Wanderly Travel", "Client needs a Vietnam e-visa for a trip in 3 weeks. Fine?"],
  [
    "wanderly",
    "Wanderly Travel",
    "Update: the Vietnam e-visa took 19 working days, not the 3 the site claims. We nearly missed it. Always allow a month.",
  ],
  [
    "wanderly",
    "Wanderly Travel",
    "Note for the file: our client Dr Okafor will not fly overnight and always books the aisle seat.",
  ],
  [
    "globetrek",
    "Globetrek Corporate",
    "Best way to get a team of six from Berlin to Lisbon in May?",
  ],
];

export async function POST() {
  try {
    const turns = [];
    for (const [org, orgName, question] of SCRIPT) {
      const reply = await answer(org, question);
      await record(org, orgName, `${org}:seed`, [
        ["user_message", question],
        ["assistant_message", reply],
      ]);
      turns.push({ org, orgName, question, reply });
    }
    return Response.json({ turns });
  } catch (e) {
    return Response.json({ error: e instanceof Error ? e.message : String(e) }, { status: 500 });
  }
}
