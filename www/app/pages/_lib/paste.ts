const API_URL = process.env.NEXT_PUBLIC_API_URL || "https://api.joinstash.ai";

export type Paste = {
  slug: string;
  title: string;
  content_type: "markdown" | "html";
  content: string;
  visibility: "public" | "unlisted";
  comments_enabled: boolean;
  view_count: number;
  created_at: string;
  updated_at: string;
};

export type PasteComment = {
  id: string;
  parent_id: string | null;
  author_name: string;
  body: string;
  quoted_text: string;
  prefix: string;
  suffix: string;
  created_at: string;
  // Only present on comments created in the current session (the create
  // response returns it once); lets the author delete their own comment
  // before a reload. Never comes back from the list endpoint.
  edit_token?: string;
};

export async function fetchPaste(slug: string): Promise<Paste | null> {
  const res = await fetch(`${API_URL}/api/v1/pastes/${encodeURIComponent(slug)}`, {
    cache: "no-store",
  });
  if (!res.ok) return null;
  return res.json();
}

export async function fetchComments(slug: string): Promise<PasteComment[]> {
  const res = await fetch(`${API_URL}/api/v1/pastes/${encodeURIComponent(slug)}/comments`, {
    cache: "no-store",
  });
  if (!res.ok) return [];
  const body = await res.json();
  return body.comments ?? [];
}
