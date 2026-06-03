import { SSR_BACKEND_ORIGIN as BACKEND_ORIGIN } from "@/lib/backendOrigin";
import type { StashPreviewData } from "./stashPreview";

export async function loadPublicStashPreview(
  slug: string,
): Promise<StashPreviewData | null> {
  const res = await fetch(`${BACKEND_ORIGIN}/api/v1/cartridges/${encodeURIComponent(slug)}`, {
    cache: "no-store",
  });
  if (!res.ok) return null;
  return res.json();
}
