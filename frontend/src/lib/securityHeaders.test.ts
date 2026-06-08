import { describe, expect, it } from "vitest";

import {
  frameGuardHeaders,
  securityHeaders,
  stashEmbedHeaders,
} from "./securityHeaders";

function asRecord(headers: { key: string; value: string }[]) {
  return Object.fromEntries(headers.map((header) => [header.key, header.value]));
}

describe("securityHeaders", () => {
  it("sets baseline browser hardening headers", () => {
    const headers = asRecord(securityHeaders);

    expect(headers["Strict-Transport-Security"]).toBe("max-age=31536000");
    expect(headers["X-Content-Type-Options"]).toBe("nosniff");
    expect(headers["Referrer-Policy"]).toBe("strict-origin-when-cross-origin");
    expect(headers["Permissions-Policy"]).toBe(
      "camera=(), microphone=(), geolocation=(), payment=()",
    );
  });

  it("blocks framing on non-embed routes", () => {
    const guard = asRecord(frameGuardHeaders);

    expect(guard["X-Frame-Options"]).toBe("DENY");
    expect(guard["Content-Security-Policy"]).toBe("frame-ancestors 'none'");
  });

  it("keeps published Stash embedding as an explicit exception", () => {
    const baseline = asRecord(securityHeaders);
    const embed = asRecord(stashEmbedHeaders);

    // Frame protection lives in frameGuardHeaders, applied to every route
    // except embeds, so the baseline and embed sets carry no X-Frame-Options.
    expect(baseline["X-Frame-Options"]).toBeUndefined();
    expect(baseline["Content-Security-Policy"]).toBeUndefined();
    expect(embed["X-Frame-Options"]).toBeUndefined();
    expect(embed["Content-Security-Policy"]).toBe("frame-ancestors *");
  });
});
