import { listOrgs } from "@/lib/stash";

export async function GET() {
  const orgs = await listOrgs();
  return Response.json({ orgs });
}
