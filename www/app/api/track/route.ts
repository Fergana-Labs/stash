import { NextResponse, type NextRequest } from "next/server";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "https://api.joinstash.ai";

// Same-origin beacon target for the message-test pages; forwards to the
// backend server-side so the browser never makes a cross-origin call.
export async function POST(request: NextRequest) {
  const body = await request.text();
  const res = await fetch(`${API_URL}/api/v1/marketing/events`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body,
  });
  return new NextResponse(null, { status: res.ok ? 204 : res.status });
}
