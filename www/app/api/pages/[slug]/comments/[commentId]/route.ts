import { NextResponse, type NextRequest } from "next/server";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "https://api.joinstash.ai";

// Agent-facing comment edit/delete on the canonical domain:
//   PATCH  joinstash.ai/pages/{slug}/comments/{id}?token=…  (comment author token)
//   DELETE joinstash.ai/pages/{slug}/comments/{id}?token=…  (comment author OR page edit token)
function commentUrl(slug: string, id: string, token: string) {
  return (
    `${API_URL}/api/v1/pastes/${encodeURIComponent(slug)}/comments/${encodeURIComponent(id)}` +
    `?token=${encodeURIComponent(token)}`
  );
}

export async function PATCH(
  request: NextRequest,
  { params }: { params: Promise<{ slug: string; commentId: string }> },
) {
  const { slug, commentId } = await params;
  const token = request.nextUrl.searchParams.get("token") ?? "";
  const contentType = request.headers.get("content-type") ?? "";
  const rawBody = await request.text();
  const payload = contentType.includes("application/json")
    ? JSON.parse(rawBody)
    : { body: rawBody };

  const res = await fetch(commentUrl(slug, commentId, token), {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  return new NextResponse(await res.text(), {
    status: res.status,
    headers: { "Content-Type": "application/json" },
  });
}

export async function DELETE(
  request: NextRequest,
  { params }: { params: Promise<{ slug: string; commentId: string }> },
) {
  const { slug, commentId } = await params;
  const token = request.nextUrl.searchParams.get("token") ?? "";
  const res = await fetch(commentUrl(slug, commentId, token), { method: "DELETE" });
  return new NextResponse(null, { status: res.status });
}
