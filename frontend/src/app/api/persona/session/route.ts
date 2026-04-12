import { type NextRequest, NextResponse } from "next/server";
import { cookies } from "next/headers";
import { getIronSession } from "iron-session";
import { type PersonaSessionData } from "@/lib/personaSession";

const BACKEND = process.env.NEXT_PUBLIC_API_URL || "http://localhost:3456";

function ironOptions() {
  const secret = process.env.SESSION_SECRET ?? "";
  return {
    password: secret.length >= 32 ? secret : secret.padEnd(32, "0"),
    cookieName: "boozle_persona",
    cookieOptions: {
      httpOnly: true,
      secure: process.env.NODE_ENV === "production",
      sameSite: "lax" as const,
      path: "/",
      maxAge: 60 * 60 * 24 * 7, // 7 days
    },
  };
}

/** GET /api/persona/session — check if a persona session is active */
export async function GET() {
  try {
    const cookieStore = await cookies();
    const session = await getIronSession<PersonaSessionData>(
      cookieStore,
      ironOptions()
    );
    if (session.apiKey) {
      return NextResponse.json({ authenticated: true });
    }
    return NextResponse.json({ authenticated: false });
  } catch {
    return NextResponse.json({ authenticated: false });
  }
}

/**
 * POST /api/persona/session — validate a persona API key with the backend and
 * store it in an encrypted httpOnly session cookie.
 * Body: { apiKey: string }
 */
export async function POST(request: NextRequest) {
  let apiKey: string;
  try {
    const body = await request.json();
    apiKey = (body.apiKey as string)?.trim();
    if (!apiKey) throw new Error("missing apiKey");
  } catch {
    return NextResponse.json({ error: "apiKey is required" }, { status: 400 });
  }

  // Validate the key against the backend
  const verifyRes = await fetch(`${BACKEND}/api/v1/users/me`, {
    headers: { Authorization: `Bearer ${apiKey}` },
  });
  if (!verifyRes.ok) {
    return NextResponse.json({ error: "Invalid API key" }, { status: 401 });
  }

  const user = await verifyRes.json();

  const cookieStore = await cookies();
  const session = await getIronSession<PersonaSessionData>(
    cookieStore,
    ironOptions()
  );
  session.apiKey = apiKey;
  await session.save();

  return NextResponse.json({ authenticated: true, user });
}

/** DELETE /api/persona/session — clear the persona session cookie */
export async function DELETE() {
  const cookieStore = await cookies();
  const session = await getIronSession<PersonaSessionData>(
    cookieStore,
    ironOptions()
  );
  session.destroy();
  return NextResponse.json({ authenticated: false });
}
