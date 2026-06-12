import { NextResponse, type NextRequest } from "next/server";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "https://api.joinstash.ai";

// Agent-facing edit endpoint, reached as
// `curl -X PATCH "joinstash.ai/pages/{slug}?token=…"` via the proxy
// rewrite. Accepts our JSON shape or a raw body that replaces the content.
export async function PATCH(
  request: NextRequest,
  { params }: { params: Promise<{ slug: string }> },
) {
  const { slug } = await params;
  const token = request.nextUrl.searchParams.get("token") ?? "";
  const contentType = request.headers.get("content-type") ?? "";
  const rawBody = await request.text();

  let payload: { title: string; content: string };
  if (contentType.includes("application/json")) {
    const body = JSON.parse(rawBody);
    payload = { title: String(body.title ?? ""), content: String(body.content ?? "") };
  } else {
    payload = { title: "", content: rawBody };
  }

  const res = await fetch(
    `${API_URL}/api/v1/pastes/${encodeURIComponent(slug)}?token=${encodeURIComponent(token)}`,
    {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    },
  );
  return new NextResponse(await res.text(), {
    status: res.status,
    headers: { "Content-Type": "application/json" },
  });
}
