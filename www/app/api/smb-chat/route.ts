import { NextResponse, type NextRequest } from "next/server";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "https://api.joinstash.ai";

// Same-origin proxy for the /smb interview chat. The LLM call (and the
// Anthropic key) live in the backend's public marketing router; this just
// forwards so the browser never makes a cross-origin call.
export async function POST(request: NextRequest) {
  const body = await request.text();
  const res = await fetch(`${API_URL}/api/v1/marketing/smb-chat`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body,
  });
  return new NextResponse(await res.text(), {
    status: res.status,
    headers: { "Content-Type": "application/json" },
  });
}
