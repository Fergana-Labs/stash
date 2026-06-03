import { SSR_BACKEND_ORIGIN as BACKEND_ORIGIN } from "@/lib/backendOrigin";
import type { CartridgePreviewData } from "./cartridgePreview";

export async function loadPublicCartridgePreview(
  slug: string,
): Promise<CartridgePreviewData | null> {
  const res = await fetch(`${BACKEND_ORIGIN}/api/v1/cartridges/${encodeURIComponent(slug)}`, {
    cache: "no-store",
  });
  if (!res.ok) return null;
  return res.json();
}
