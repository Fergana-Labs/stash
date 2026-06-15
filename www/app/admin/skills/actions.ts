"use server";

import { revalidatePath } from "next/cache";

// Mutations run server-side so the admin token (ADMIN_PASSWORD) never reaches
// the client. The /admin/* cookie gate in proxy.ts already authenticated the
// operator before these actions can run.

const apiUrl = process.env.NEXT_PUBLIC_API_URL || "http://localhost:3456";

export type ActionResult = { ok: true; message: string } | { ok: false; message: string };

async function callAdmin(path: string, repoUrl: string): Promise<ActionResult> {
  const token = process.env.ADMIN_PASSWORD;
  if (!token) return { ok: false, message: "ADMIN_PASSWORD is not set on the www server." };
  const res = await fetch(`${apiUrl}${path}`, {
    method: "POST",
    headers: { "X-Admin-Token": token, "Content-Type": "application/json" },
    body: JSON.stringify({ repo_url: repoUrl }),
    cache: "no-store",
  });
  const body = await res.json().catch(() => ({}));
  if (!res.ok) {
    return { ok: false, message: body.detail || `Request failed (${res.status})` };
  }
  revalidatePath("/admin/skills");
  return { ok: true, message: summarize(path, body) };
}

function summarize(path: string, body: Record<string, unknown>): string {
  if (path.endsWith("/remove")) {
    return `Removed ${body.removed} skill${body.removed === 1 ? "" : "s"}.`;
  }
  return `Imported ${body.skills_found} skill${body.skills_found === 1 ? "" : "s"} (${body.created} new, ${body.updated} updated).`;
}

export async function importRepo(_prev: ActionResult | null, formData: FormData): Promise<ActionResult> {
  const repoUrl = String(formData.get("repo_url") ?? "").trim();
  if (!repoUrl) return { ok: false, message: "Enter a GitHub repo URL." };
  return callAdmin("/api/v1/admin/discover-skills/import", repoUrl);
}

export async function removeRepo(repoUrl: string): Promise<ActionResult> {
  return callAdmin("/api/v1/admin/discover-skills/remove", repoUrl);
}
