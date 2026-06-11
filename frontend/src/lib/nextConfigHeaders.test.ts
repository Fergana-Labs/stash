import fs from "node:fs";
import path from "node:path";

import { describe, expect, it } from "vitest";

// The securityHeaders tests only check header values; this pins the route
// binding, because pointing the frame-ancestors * exception at a path with no
// page would silently serve the real embed page the deny-framing baseline and
// break every published Skill iframe embed.
describe("next.config frame headers", () => {
  it("re-opens framing exactly on the embed route that exists in the app", async () => {
    process.env.BACKEND_INTERNAL_URL ||= "http://backend:3456";
    const { default: nextConfig } = await import("../../next.config");
    const rules = await nextConfig.headers!();

    const embedRule = rules.find((rule) =>
      rule.headers.some((header) => header.value === "frame-ancestors *"),
    );
    expect(embedRule?.source).toBe("/skills/:slug/embed");

    const embedPage = path.join(__dirname, "../app/(app)/skills/[slug]/embed/page.tsx");
    expect(fs.existsSync(embedPage)).toBe(true);

    // Next.js applies later header rules over earlier ones for the same key,
    // so the embed exception must come after the deny-framing baseline.
    const baselineIndex = rules.findIndex((rule) => rule.source === "/:path*");
    expect(baselineIndex).toBeGreaterThanOrEqual(0);
    expect(rules.indexOf(embedRule!)).toBeGreaterThan(baselineIndex);
  });
});
