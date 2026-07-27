import { describe, expect, it } from "vitest";

import { displayTimestamp } from "./cells";

describe("displayTimestamp", () => {
  it("turns stored ISO timestamps into readable calendar dates", () => {
    expect(displayTimestamp("2026-07-26T10:15:00Z")).not.toContain("T10:15:00");
    expect(displayTimestamp("2026-07-26T10:15:00Z")).toContain("2026");
  });
});
