import { listTenants } from "@/lib/stash";

export async function GET() {
  try {
    return Response.json({ tenants: await listTenants() });
  } catch (e) {
    return Response.json({ error: e instanceof Error ? e.message : String(e) }, { status: 500 });
  }
}
