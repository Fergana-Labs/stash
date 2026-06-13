import { NextResponse, type NextRequest } from "next/server";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "https://api.joinstash.ai";

// Agent-facing comment list/add on the canonical domain:
//   GET  joinstash.ai/pages/{slug}/comments
//   POST joinstash.ai/pages/{slug}/comments   (raw text body = the comment)
function commentsUrl(slug: string) {
  return `${API_URL}/api/v1/pastes/${encodeURIComponent(slug)}/comments`;
}

export async function GET(
  _request: NextRequest,
  { params }: { params: Promise<{ slug: string }> },
) {
  const { slug } = await params;
  const res = await fetch(commentsUrl(slug), { cache: "no-store" });
  return new NextResponse(await res.text(), {
    status: res.status,
    headers: { "Content-Type": "application/json" },
  });
}

export async function POST(
  request: NextRequest,
  { params }: { params: Promise<{ slug: string }> },
) {
  const { slug } = await params;
  const contentType = request.headers.get("content-type") ?? "";
  const rawBody = await request.text();
  const payload = contentType.includes("application/json")
    ? JSON.parse(rawBody)
    : { body: rawBody };

  const res = await fetch(commentsUrl(slug), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  return new NextResponse(await res.text(), {
    status: res.status,
    headers: { "Content-Type": "application/json" },
  });
}
