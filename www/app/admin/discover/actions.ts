"use server";

import { revalidatePath } from "next/cache";

type CatalogAction = "list" | "unlist" | "feature" | "unfeature";

function apiConfig() {
  const apiUrl = process.env.NEXT_PUBLIC_API_URL || "http://localhost:3456";
  const token = process.env.ADMIN_PASSWORD;
  if (!token) {
    throw new Error("ADMIN_PASSWORD env var is not set on the www server.");
  }
  return { apiUrl, token };
}

export async function updateDiscoverWorkspace(formData: FormData) {
  const workspaceId = String(formData.get("workspace_id") ?? "");
  const action = String(formData.get("action") ?? "") as CatalogAction;
  if (!workspaceId) throw new Error("workspace_id is required");

  const body =
    action === "list"
      ? { discoverable: true }
      : action === "unlist"
        ? { discoverable: false }
        : action === "feature"
          ? { discoverable: true, featured: true }
          : action === "unfeature"
            ? { featured: false }
            : null;

  if (!body) throw new Error("Unsupported Discover action");

  const { apiUrl, token } = apiConfig();
  const res = await fetch(`${apiUrl}/api/v1/admin/discover/workspaces/${workspaceId}`, {
    method: "PATCH",
    headers: {
      "Content-Type": "application/json",
      "X-Admin-Token": token,
    },
    body: JSON.stringify(body),
    cache: "no-store",
  });

  if (!res.ok) {
    throw new Error(await res.text());
  }

  revalidatePath("/admin/discover");
}
