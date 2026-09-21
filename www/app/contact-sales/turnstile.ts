export async function verifyTurnstile(token: FormDataEntryValue | null): Promise<boolean> {
  if (typeof token !== "string" || !token || token.length > 2048) return false;

  const secret = process.env.TURNSTILE_SECRET_KEY;
  const hostname = process.env.TURNSTILE_HOSTNAME;
  if (!secret || !hostname) {
    throw new Error("TURNSTILE_SECRET_KEY and TURNSTILE_HOSTNAME are required");
  }

  const response = await fetch("https://challenges.cloudflare.com/turnstile/v0/siteverify", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ secret, response: token }),
    signal: AbortSignal.timeout(10_000),
  });
  if (!response.ok) throw new Error(`Turnstile verification failed: ${response.status}`);

  const result = await response.json();
  return result.success === true && result.hostname === hostname && result.action === "contact_sales";
}
