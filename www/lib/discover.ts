const API_URL = process.env.NEXT_PUBLIC_API_URL || "https://api.joinstash.ai";
export const APP_URL = process.env.MANAGED_APP_URL || "https://app.joinstash.ai";

export type CatalogCard = {
  id: string;
  name: string;
  summary: string | null;
  description: string;
  is_public: boolean;
  tags: string[];
  category: string | null;
  featured: boolean;
  cover_image_url: string | null;
  creator_id: string;
  creator_name: string;
  creator_display_name: string | null;
  member_count: number;
  fork_count: number;
  notebook_count: number;
  table_count: number;
  file_count: number;
  history_event_count: number;
  forked_from_workspace_id: string | null;
  created_at: string;
  updated_at: string;
};

export type CatalogPage = {
  workspaces: CatalogCard[];
  next_cursor: string | null;
};

type Params = {
  q?: string;
  category?: string;
  tag?: string;
  sort?: "trending" | "newest" | "forks";
  cursor?: string;
};

export async function fetchCatalog(params: Params = {}): Promise<CatalogPage> {
  const qs = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) {
    if (v) qs.set(k, v);
  }
  const url = `${API_URL}/api/v1/discover/workspaces${qs.size ? `?${qs.toString()}` : ""}`;
  const res = await fetch(url, { next: { revalidate: 60 } });
  if (!res.ok) {
    return { workspaces: [], next_cursor: null };
  }
  return res.json();
}
