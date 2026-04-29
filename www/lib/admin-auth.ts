// HMAC-signed session cookies using Web Crypto so this works in both
// the Edge runtime (proxy.ts) and the Node runtime (server actions).

export const ADMIN_COOKIE_NAME = "__stash_admin";
export const SESSION_TTL_SECONDS = 7 * 24 * 60 * 60;

function getSecret(): string {
  const secret = process.env.ADMIN_COOKIE_SECRET;
  if (!secret || secret.length < 16) {
    throw new Error("ADMIN_COOKIE_SECRET must be set (32+ chars recommended)");
  }
  return secret;
}

async function importKey(secret: string): Promise<CryptoKey> {
  return crypto.subtle.importKey(
    "raw",
    new TextEncoder().encode(secret),
    { name: "HMAC", hash: "SHA-256" },
    false,
    ["sign", "verify"],
  );
}

function bytesToHex(bytes: ArrayBuffer): string {
  return [...new Uint8Array(bytes)]
    .map((b) => b.toString(16).padStart(2, "0"))
    .join("");
}

function hexToBuffer(hex: string): ArrayBuffer {
  if (hex.length % 2 !== 0) return new ArrayBuffer(0);
  const buf = new ArrayBuffer(hex.length / 2);
  const view = new Uint8Array(buf);
  for (let i = 0; i < view.length; i++) {
    view[i] = parseInt(hex.substr(i * 2, 2), 16);
  }
  return buf;
}

export async function signSession(): Promise<string> {
  const exp = Math.floor(Date.now() / 1000) + SESSION_TTL_SECONDS;
  const payload = String(exp);
  const key = await importKey(getSecret());
  const sig = await crypto.subtle.sign("HMAC", key, new TextEncoder().encode(payload));
  return `${payload}.${bytesToHex(sig)}`;
}

export async function verifySession(value: string | undefined): Promise<boolean> {
  if (!value) return false;
  const dot = value.indexOf(".");
  if (dot < 1) return false;
  const payload = value.slice(0, dot);
  const sigHex = value.slice(dot + 1);
  const exp = Number(payload);
  if (!Number.isFinite(exp)) return false;
  if (Math.floor(Date.now() / 1000) >= exp) return false;

  const key = await importKey(getSecret());
  return crypto.subtle.verify(
    "HMAC",
    key,
    hexToBuffer(sigHex),
    new TextEncoder().encode(payload),
  );
}

export function checkPassword(submitted: string): boolean {
  const expected = process.env.ADMIN_PASSWORD;
  if (!expected) return false;
  if (submitted.length !== expected.length) return false;
  // Constant-time compare in JS is best-effort; same-length XOR loop.
  let diff = 0;
  for (let i = 0; i < expected.length; i++) {
    diff |= submitted.charCodeAt(i) ^ expected.charCodeAt(i);
  }
  return diff === 0;
}
