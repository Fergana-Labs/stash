import { type NextRequest } from "next/server";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "https://api.joinstash.ai";

// Raw source for a paste. HTML is deliberately served as text/plain —
// serving user HTML as text/html on this origin would be stored XSS
// (the /admin cookie lives here). Rendered viewing is the sandboxed
// iframe on the page itself.
export async function GET(
  _request: NextRequest,
  { params }: { params: Promise<{ slug: string }> },
) {
  const { slug } = await params;
  const res = await fetch(`${API_URL}/api/v1/pastes/${encodeURIComponent(slug)}`, {
    cache: "no-store",
  });
  if (!res.ok) return new Response("Not found", { status: 404 });
  const paste = await res.json();
  const mediaType = paste.content_type === "markdown" ? "text/markdown" : "text/plain";
  return new Response(paste.content, {
    headers: {
      "Content-Type": `${mediaType}; charset=utf-8`,
      "X-Content-Type-Options": "nosniff",
    },
  });
}
