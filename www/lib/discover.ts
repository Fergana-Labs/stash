const API_URL = process.env.NEXT_PUBLIC_API_URL || "https://api.joinstash.ai";
export const APP_URL = process.env.MANAGED_APP_URL || "https://app.joinstash.ai";

export type PublicSkillCard = {
  id: string;
  slug: string;
  title: string;
  description: string;
  discoverable: boolean;
  cover_image_url: string | null;
  source_github_url: string | null;
  view_count: number;
  owner_name: string;
  owner_display_name: string | null;
  workspace_id: string;
  workspace_name: string;
  item_count: number;
  created_at: string;
  updated_at: string;
};

type CatalogPage = {
  skills: PublicSkillCard[];
};

type Params = {
  q?: string;
  sort?: "trending" | "newest" | "popular";
};

export async function fetchCatalog(params: Params = {}): Promise<CatalogPage> {
  const qs = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) {
    if (v) qs.set(k, v);
  }
  const url = `${API_URL}/api/v1/discover/skills${qs.size ? `?${qs.toString()}` : ""}`;
  const res = await fetch(url, { next: { revalidate: 60 } });
  if (!res.ok) {
    return { skills: [] };
  }
  return res.json();
}
