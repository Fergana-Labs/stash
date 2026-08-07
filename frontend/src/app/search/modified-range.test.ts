import { describe, expect, it } from "vitest";
import {
  DEFAULT_MODIFIED_RANGE,
  modifiedRangeLabel,
  modifiedRangeParams,
  withinModifiedRange,
  type ModifiedRange,
} from "./modified-range";

const NOW = new Date("2026-07-24T12:00:00Z");

function custom(from: string, to: string): ModifiedRange {
  return { preset: "custom", from, to };
}

describe("modifiedRangeParams", () => {
  it("sends nothing for the default range", () => {
    expect(modifiedRangeParams(DEFAULT_MODIFIED_RANGE, NOW)).toEqual({});
  });

  it("anchors each relative preset to now, with no upper bound", () => {
    const cases: Array<[ModifiedRange["preset"], string]> = [
      ["24h", "2026-07-23T12:00:00.000Z"],
      ["week", "2026-07-17T12:00:00.000Z"],
      ["month", "2026-06-24T12:00:00.000Z"],
      ["year", "2025-07-24T12:00:00.000Z"],
    ];
    for (const [preset, expected] of cases) {
      expect(modifiedRangeParams({ preset, from: "", to: "" }, NOW)).toEqual({
        modifiedAfter: expected,
      });
    }
  });

  it("converts custom datetime-local values from local time to UTC ISO", () => {
    const bounds = modifiedRangeParams(custom("2026-07-01T09:30", "2026-07-20T18:00"), NOW);
    // new Date(value) parses datetime-local strings as local time, so the
    // expected ISO is whatever that conversion yields in this environment.
    expect(bounds).toEqual({
      modifiedAfter: new Date("2026-07-01T09:30").toISOString(),
      modifiedBefore: new Date("2026-07-20T18:00").toISOString(),
    });
  });

  it("sends only the bound that is filled in", () => {
    expect(modifiedRangeParams(custom("2026-07-01T09:30", ""), NOW)).toEqual({
      modifiedAfter: new Date("2026-07-01T09:30").toISOString(),
    });
    expect(modifiedRangeParams(custom("", "2026-07-20T18:00"), NOW)).toEqual({
      modifiedBefore: new Date("2026-07-20T18:00").toISOString(),
    });
    expect(modifiedRangeParams(custom("", ""), NOW)).toEqual({});
  });
});

describe("withinModifiedRange", () => {
  const bounds = {
    modifiedAfter: "2026-02-01T00:00:00Z",
    modifiedBefore: "2026-03-01T00:00:00Z",
  };

  it("keeps everything when no bounds are set", () => {
    expect(withinModifiedRange(null, {})).toBe(true);
    expect(withinModifiedRange("2020-01-01T00:00:00Z", {})).toBe(true);
  });

  it("excludes results with no timestamp whenever a bound is set", () => {
    expect(withinModifiedRange(null, { modifiedAfter: bounds.modifiedAfter })).toBe(false);
    expect(withinModifiedRange(undefined, { modifiedBefore: bounds.modifiedBefore })).toBe(false);
  });

  it("applies strict bounds, matching the server", () => {
    expect(withinModifiedRange("2026-02-15T00:00:00Z", bounds)).toBe(true);
    expect(withinModifiedRange("2026-01-15T00:00:00Z", bounds)).toBe(false);
    expect(withinModifiedRange("2026-03-15T00:00:00Z", bounds)).toBe(false);
    expect(withinModifiedRange(bounds.modifiedAfter, bounds)).toBe(false);
    expect(withinModifiedRange(bounds.modifiedBefore, bounds)).toBe(false);
  });
});

describe("modifiedRangeLabel", () => {
  it("labels each preset for the chip", () => {
    expect(modifiedRangeLabel(DEFAULT_MODIFIED_RANGE)).toBe("Any time");
    expect(modifiedRangeLabel({ preset: "24h", from: "", to: "" })).toBe("Past 24 hours");
    expect(modifiedRangeLabel({ preset: "week", from: "", to: "" })).toBe("Past week");
    expect(modifiedRangeLabel(custom("2026-07-01T09:30", ""))).toBe("Custom range");
  });
});
