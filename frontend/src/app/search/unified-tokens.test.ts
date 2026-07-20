/** The unified call must carry exactly the sources chip's selection minus the
 * client-side kinds (skills/tables never reach the API) — and be skipped
 * entirely (null) when nothing API-searchable is selected, so no wasted server
 * round-trip and no results the user filtered out. */
import { describe, expect, it } from "vitest";
import { unifiedSearchTokens } from "./unified-tokens";

const ALL = ["files", "sessions", "skills", "tables", "gmail", "jira"];

describe("unifiedSearchTokens", () => {
  it("passes the selection through minus the client-side kinds", () => {
    expect(unifiedSearchTokens({ filtered: false }, ALL)).toEqual([
      "files",
      "sessions",
      "gmail",
      "jira",
    ]);
  });

  it("keeps a provider-only selection intact", () => {
    expect(unifiedSearchTokens({ filtered: false }, ["gmail"])).toEqual(["gmail"]);
  });

  it("skips the call when only client-side kinds are selected", () => {
    expect(unifiedSearchTokens({ filtered: false }, ["skills", "tables"])).toBeNull();
  });

  it("skips the call when nothing is selected", () => {
    expect(unifiedSearchTokens({ filtered: false }, [])).toBeNull();
  });

  it("narrows to files under a folder/page filter", () => {
    expect(unifiedSearchTokens({ filtered: true }, ALL)).toEqual(["files"]);
    expect(unifiedSearchTokens({ filtered: true }, ["sessions", "gmail"])).toBeNull();
  });
});
