import { describe, expect, it } from "vitest";

import { securityHeaders, skillEmbedHeaders } from "./securityHeaders";

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

  it("keeps published Skill embedding as an explicit exception", () => {
    const baseline = asRecord(securityHeaders);
    const embed = asRecord(skillEmbedHeaders);

    expect(baseline["Content-Security-Policy"]).toBeUndefined();
    expect(embed["Content-Security-Policy"]).toBe("frame-ancestors *");
  });
});
