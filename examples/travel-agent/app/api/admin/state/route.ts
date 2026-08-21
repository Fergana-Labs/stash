import { listSessionRows, read } from "@/lib/stash";
import { TRAVELLERS } from "@/lib/travellers";

// What the demo currently looks like: every traveller's chats, and the shared
// wiki, each read through that traveller's own view.
export async function GET() {
  try {
    const travellers = [];
    for (const traveller of TRAVELLERS) {
      const sessions = await listSessionRows(traveller.id);
      travellers.push({ ...traveller, chats: sessions.map((s) => s.title || s.sessionId) });
    }
    const wiki = (await read(TRAVELLERS[0].id, "ls /memory"))
      .split("\n")
      .map((line) => line.trim())
      .filter(Boolean);
    return Response.json({ travellers, wiki });
  } catch (e) {
    console.error("[admin] state failed:", e);
    return Response.json({ error: "Could not read the demo's state." }, { status: 500 });
  }
}
