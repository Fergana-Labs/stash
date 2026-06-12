import { NextResponse, type NextRequest } from "next/server";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "https://api.joinstash.ai";

const HTML_START_RE = /^\s*(<!doctype|<html)/i;

// Agent-facing create endpoint, reached as `curl -X POST joinstash.ai/pages`
// via the proxy rewrite. Accepts either our JSON shape or a raw body
// (markdown or HTML, auto-detected) with options in the query string —
// ?title=…&visibility=unlisted&editable=true — and forwards to the
// backend server-side, so the response can hand back ready-to-use www URLs.
export async function POST(request: NextRequest) {
  const contentType = request.headers.get("content-type") ?? "";
  const rawBody = await request.text();
  const query = request.nextUrl.searchParams;

  let payload: {
    title: string;
    content: string;
    content_type: string;
    visibility: string;
    public_edit: boolean;
  };
  if (contentType.includes("application/json")) {
    const body = JSON.parse(rawBody);
    payload = {
      title: String(body.title ?? ""),
      content: String(body.content ?? ""),
      content_type: String(body.content_type ?? "markdown"),
      visibility: String(body.visibility ?? "public"),
      public_edit: body.public_edit === true,
    };
  } else {
    const isHtml = contentType.includes("text/html") || HTML_START_RE.test(rawBody);
    payload = {
      title: query.get("title") ?? "",
      content: rawBody,
      content_type: isHtml ? "html" : "markdown",
      visibility: query.get("visibility") ?? "public",
      public_edit: query.get("editable") === "true",
    };
  }

  const res = await fetch(`${API_URL}/api/v1/pastes`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!res.ok) {
    return new NextResponse(await res.text(), { status: res.status });
  }

  const paste = await res.json();
  const origin = request.nextUrl.origin;
  const viewUrl = `${origin}/pages/${paste.slug}`;
  return NextResponse.json(
    {
      slug: paste.slug,
      title: paste.title,
      content_type: paste.content_type,
      visibility: paste.visibility,
      public_edit: paste.public_edit,
      view_url: viewUrl,
      edit_url: paste.public_edit
        ? `${viewUrl}/edit`
        : `${viewUrl}/edit?token=${paste.edit_token}`,
      raw_url: `${viewUrl}/raw`,
    },
    { status: 201 },
  );
}
