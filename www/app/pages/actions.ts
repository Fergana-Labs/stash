"use server";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "https://api.joinstash.ai";

export type PasteContentType = "markdown" | "html";
export type PasteVisibility = "public" | "unlisted";

export type CreatePasteResult =
  | {
      status: "ok";
      slug: string;
      title: string;
      content_type: PasteContentType;
      edit_token: string;
    }
  | { status: "error"; message: string };

export async function createPaste(input: {
  title: string;
  content: string;
  content_type: PasteContentType;
  visibility: PasteVisibility;
}): Promise<CreatePasteResult> {
  const res = await fetch(`${API_URL}/api/v1/pastes`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(input),
  });
  if (!res.ok) {
    const message =
      res.status === 429
        ? "Too many pages created — try again in a minute."
        : "Could not publish the page. Try again.";
    return { status: "error", message };
  }
  const paste = await res.json();
  return {
    status: "ok",
    slug: paste.slug,
    title: paste.title,
    content_type: paste.content_type,
    edit_token: paste.edit_token,
  };
}

export type AddCommentResult =
  | { status: "ok"; comment: unknown }
  | { status: "error"; message: string };

export async function addComment(
  slug: string,
  input: {
    author_name: string;
    body: string;
    quoted_text: string;
    prefix: string;
    suffix: string;
  },
): Promise<AddCommentResult> {
  const res = await fetch(`${API_URL}/api/v1/pastes/${encodeURIComponent(slug)}/comments`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(input),
  });
  if (!res.ok) {
    const message =
      res.status === 429
        ? "Too many comments — try again in a minute."
        : "Could not post the comment. Try again.";
    return { status: "error", message };
  }
  return { status: "ok", comment: await res.json() };
}

export type UpdatePasteResult = { status: "ok" } | { status: "error"; message: string };

export async function deletePaste(slug: string, token: string): Promise<UpdatePasteResult> {
  const res = await fetch(
    `${API_URL}/api/v1/pastes/${encodeURIComponent(slug)}?token=${encodeURIComponent(token)}`,
    { method: "DELETE" },
  );
  if (res.status === 404) {
    return { status: "error", message: "Invalid edit link — could not delete." };
  }
  if (!res.ok) {
    return { status: "error", message: "Delete failed. Try again." };
  }
  return { status: "ok" };
}

export async function updatePaste(
  slug: string,
  token: string,
  input: { content?: string; comments_enabled?: boolean },
): Promise<UpdatePasteResult> {
  const res = await fetch(
    `${API_URL}/api/v1/pastes/${encodeURIComponent(slug)}?token=${encodeURIComponent(token)}`,
    {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(input),
    },
  );
  if (res.status === 404) {
    return { status: "error", message: "Invalid edit link — changes are not being saved." };
  }
  if (!res.ok) {
    return { status: "error", message: "Save failed. Try again." };
  }
  return { status: "ok" };
}
