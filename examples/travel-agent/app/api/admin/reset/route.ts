import { SAM_SESSION, SAM_TURNS } from "@/lib/fixture";
import { listSessionRows, purgeSession, record } from "@/lib/stash";
import { travellerById, TRAVELLERS } from "@/lib/travellers";

/**
 * Put the demo back to its opening position: Sam has been through the Vietnam
 * e-visa the hard way, Priya has never mentioned Vietnam.
 *
 * The shared wiki is left alone. It is what the curator already built out of
 * Sam's lesson, and it is what makes Priya's first question land — rebuilding
 * it would mean another curator run.
 */
export async function POST() {
  try {
    let purged = 0;
    for (const traveller of TRAVELLERS) {
      for (const session of await listSessionRows(traveller.id)) {
        await purgeSession(session.id);
        purged += 1;
      }
    }

    const sam = travellerById("sam");
    await record(
      sam.id,
      sam.name,
      SAM_SESSION,
      SAM_TURNS.flatMap(([question, reply]): [string, string][] => [
        ["user_message", question],
        ["assistant_message", reply],
      ]),
    );

    return Response.json({ purged, restored: SAM_TURNS.length });
  } catch (e) {
    console.error("[admin] reset failed:", e);
    return Response.json({ error: "Reset failed — see the server log." }, { status: 500 });
  }
}
