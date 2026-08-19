import { listOrgs } from "@/lib/stash";

export async function GET() {
  try {
    return Response.json({ orgs: await listOrgs() });
  } catch (e) {
    return Response.json({ error: e instanceof Error ? e.message : String(e) }, { status: 500 });
  }
}
