"use server";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "https://api.joinstash.ai";

export type PasteContentType = "markdown" | "html";

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

export type UpdatePasteResult = { status: "ok" } | { status: "error"; message: string };

export async function updatePaste(
  slug: string,
  token: string,
  content: string,
): Promise<UpdatePasteResult> {
  const res = await fetch(
    `${API_URL}/api/v1/pastes/${encodeURIComponent(slug)}?token=${encodeURIComponent(token)}`,
    {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ content }),
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
