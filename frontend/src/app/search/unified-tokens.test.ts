/** The unified call must search exactly the intersection of the content-type
 * chip (result kind) and the sources chip (origin) — and be skipped entirely
 * (null) when that intersection is empty, so no wasted server round-trip and
 * no results the user filtered out. */
import { describe, expect, it } from "vitest";
import { unifiedSearchTokens } from "./unified-tokens";

const ALL = ["files", "sessions", "gmail", "jira"];

describe("unifiedSearchTokens", () => {
  it("passes the full selection through for the all scope", () => {
    expect(unifiedSearchTokens("all", { filtered: false }, ALL)).toEqual(ALL);
  });

  it("keeps a provider-only selection intact", () => {
    expect(unifiedSearchTokens("all", { filtered: false }, ["gmail"])).toEqual(["gmail"]);
  });

  it("narrows the pages scope to the files token", () => {
    expect(unifiedSearchTokens("pages", { filtered: false }, ALL)).toEqual(["files"]);
  });

  it("narrows the sessions scope to the sessions token", () => {
    expect(unifiedSearchTokens("sessions", { filtered: false }, ALL)).toEqual(["sessions"]);
  });

  it("skips the call when the scope's token is deselected", () => {
    expect(unifiedSearchTokens("pages", { filtered: false }, ["sessions", "gmail"])).toBeNull();
    expect(unifiedSearchTokens("sessions", { filtered: false }, ["files"])).toBeNull();
  });

  it("skips the call when nothing is selected", () => {
    expect(unifiedSearchTokens("all", { filtered: false }, [])).toBeNull();
  });

  it("skips the call for client-side-only scopes", () => {
    expect(unifiedSearchTokens("tables", { filtered: false }, ALL)).toBeNull();
    expect(unifiedSearchTokens("skills", { filtered: false }, ALL)).toBeNull();
  });

  it("narrows to files under a folder/page filter", () => {
    expect(unifiedSearchTokens("all", { filtered: true }, ALL)).toEqual(["files"]);
    expect(unifiedSearchTokens("sessions", { filtered: true }, ALL)).toBeNull();
    expect(unifiedSearchTokens("all", { filtered: true }, ["gmail"])).toBeNull();
  });
});
