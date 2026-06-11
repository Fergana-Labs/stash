import { SSR_BACKEND_ORIGIN as BACKEND_ORIGIN } from "@/lib/backendOrigin";
import type { SkillPreviewData } from "./skillPreview";

export async function loadPublicSkillPreview(
  slug: string,
): Promise<SkillPreviewData | null> {
  const res = await fetch(`${BACKEND_ORIGIN}/api/v1/skills/${encodeURIComponent(slug)}`, {
    cache: "no-store",
  });
  if (!res.ok) return null;
  return res.json();
}
