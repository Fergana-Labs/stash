import { expect, it } from "vitest";
import { bestWebsiteRevision, websiteDemoData } from "./website-demo-data";

import { demoFixture } from "./website-demo-fixture";

it("keeps an earlier winner when a later agent candidate regresses", () => {
  expect(bestWebsiteRevision(demoFixture.artifacts).iteration).toBe(1);
});

it("rejects corrupt receipts and non-PNG preview URLs instead of rendering arbitrary content", () => {
  expect(websiteDemoData(demoFixture)).not.toBeNull();
  for (const image of [
    "https://external.test/track",
    "data:image/svg+xml,<svg onload='alert(1)'/>",
    "javascript:alert(1)",
  ]) {
    expect(
      websiteDemoData({
        ...demoFixture,
        artifacts: [{ ...demoFixture.artifacts[0], image }],
      }),
    ).toBeNull();
  }
  expect(
    websiteDemoData({
      ...demoFixture,
      artifacts: [{ ...demoFixture.artifacts[0], score: NaN }],
    }),
  ).toBeNull();
  expect(
    websiteDemoData({
      ...demoFixture,
      artifacts: [demoFixture.artifacts[0], demoFixture.artifacts[0]],
    }),
  ).toBeNull();
});
