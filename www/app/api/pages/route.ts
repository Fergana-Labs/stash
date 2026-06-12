import { NextResponse, type NextRequest } from "next/server";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "https://api.joinstash.ai";

const HTML_START_RE = /^\s*(<!doctype|<html)/i;

// Agent-facing create endpoint, reached as `curl -X POST joinstash.ai/pages`
// via the proxy rewrite. Accepts either our JSON shape or a raw body
// (markdown or HTML, auto-detected) and forwards to the backend
// server-side, so the response can hand back ready-to-use www URLs.
export async function POST(request: NextRequest) {
  const contentType = request.headers.get("content-type") ?? "";
  const rawBody = await request.text();

  let payload: { title: string; content: string; content_type: string };
  if (contentType.includes("application/json")) {
    const body = JSON.parse(rawBody);
    payload = {
      title: String(body.title ?? ""),
      content: String(body.content ?? ""),
      content_type: String(body.content_type ?? "markdown"),
    };
  } else {
    const isHtml = contentType.includes("text/html") || HTML_START_RE.test(rawBody);
    payload = { title: "", content: rawBody, content_type: isHtml ? "html" : "markdown" };
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
      view_url: viewUrl,
      edit_url: `${viewUrl}/edit?token=${paste.edit_token}`,
      raw_url: `${viewUrl}/raw`,
    },
    { status: 201 },
  );
}
