import { describe, it, expect } from "vitest";
import { parseCsv, inferColumnType, detectDelimiter } from "./csv";

describe("parseCsv", () => {
  it("handles empty cells without column shift", () => {
    expect(parseCsv("a,,b\n1,,3")).toEqual([
      ["a", "", "b"],
      ["1", "", "3"],
    ]);
  });

  it("preserves commas inside quoted fields", () => {
    expect(parseCsv('a,"b,c",d')).toEqual([["a", "b,c", "d"]]);
  });

  it("handles escaped quotes (RFC double-quote)", () => {
    expect(parseCsv('"hello ""world"""')).toEqual([['hello "world"']]);
  });

  it("handles embedded newlines inside quoted fields", () => {
    expect(parseCsv('a,"line1\nline2",c')).toEqual([
      ["a", "line1\nline2", "c"],
    ]);
  });

  it("handles CRLF line endings without trailing carriage returns", () => {
    expect(parseCsv("a,b\r\n1,2\r\n")).toEqual([
      ["a", "b"],
      ["1", "2"],
    ]);
  });

  it("strips UTF-8 BOM", () => {
    expect(parseCsv("﻿a,b\n1,2")).toEqual([
      ["a", "b"],
      ["1", "2"],
    ]);
  });

  it("does not trim whitespace inside fields", () => {
    expect(parseCsv("  spaced  ,trim me  ")).toEqual([["  spaced  ", "trim me  "]]);
  });

  it("drops a trailing empty row from a final newline", () => {
    expect(parseCsv("a,b\n1,2\n")).toEqual([
      ["a", "b"],
      ["1", "2"],
    ]);
  });

  it("keeps genuinely-empty quoted rows", () => {
    expect(parseCsv('a,b\n"",""')).toEqual([
      ["a", "b"],
      ["", ""],
    ]);
  });
});

describe("parseCsv with delimiter", () => {
  it("parses TSV when given a tab delimiter", () => {
    expect(parseCsv("a\tb\tc\n1\t2\t3", "\t")).toEqual([
      ["a", "b", "c"],
      ["1", "2", "3"],
    ]);
  });

  it("preserves commas in TSV values", () => {
    expect(parseCsv("name\tquote\nAlice\tHello, world", "\t")).toEqual([
      ["name", "quote"],
      ["Alice", "Hello, world"],
    ]);
  });
});

describe("detectDelimiter", () => {
  it("picks tab when the first line has more tabs than commas", () => {
    expect(detectDelimiter("a\tb\tc\n1\t2\t3")).toBe("\t");
  });

  it("picks comma by default (including ties)", () => {
    expect(detectDelimiter("a,b,c\n1,2,3")).toBe(",");
    expect(detectDelimiter("a\tb,c")).toBe(",");
  });

  it("handles single-column pastes", () => {
    expect(detectDelimiter("hello\nworld")).toBe(",");
  });
});

describe("inferColumnType", () => {
  it("detects boolean from yes/no/true/false", () => {
    expect(inferColumnType(["true", "false", "yes", "no"])).toBe("boolean");
  });

  it("detects number with currency, commas, percent", () => {
    expect(inferColumnType(["1", "2.5", "$1,234.50", "-3", "12%"])).toBe(
      "number",
    );
  });

  it("detects date (no time component)", () => {
    expect(inferColumnType(["2026-01-01", "2026-05-21"])).toBe("date");
  });

  it("detects datetime when every value has T", () => {
    expect(inferColumnType(["2026-01-01T10:00:00Z", "2026-05-21T00:00:00+00:00"])).toBe(
      "datetime",
    );
  });

  it("falls back to text on mixed", () => {
    expect(inferColumnType(["1", "hello"])).toBe("text");
  });

  it("ignores empty samples for inference", () => {
    expect(inferColumnType(["", "42", "", "7"])).toBe("number");
  });

  it("returns text when all samples are empty", () => {
    expect(inferColumnType(["", "", ""])).toBe("text");
  });
});
