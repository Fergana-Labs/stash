import { describe, expect, it } from "vitest";
import { isLinkDrop, targetHref } from "./hopper";
import type { HopperItem } from "./api";

// One box takes both links and notes, so this classification decides which
// pipeline a drop enters. Getting it wrong either fetches a webpage the user
// meant to jot down, or files a URL as a note nobody will ever fetch.
describe("isLinkDrop", () => {
  it("treats a bare URL as a link", () => {
    expect(isLinkDrop("https://example.com/post")).toBe(true);
    expect(isLinkDrop("  http://example.com  ")).toBe(true);
  });

  it("treats prose that merely mentions a URL as a note", () => {
    expect(isLinkDrop("read https://example.com later")).toBe(false);
    expect(isLinkDrop("Pricing call notes")).toBe(false);
    expect(isLinkDrop("")).toBe(false);
  });
});

function item(target: HopperItem["target"]): HopperItem {
  return {
    id: "1",
    kind: "link",
    label: "x",
    status: "legible",
    detail: "",
    preview: "",
    target,
    created_at: "",
  };
}

describe("targetHref", () => {
  it("links a landed drop to the page or file it became", () => {
    expect(targetHref(item({ kind: "page", id: "p1", name: "n" }))).toBe("/p/p1");
    expect(targetHref(item({ kind: "file", id: "f1", name: "n" }))).toBe("/f/f1");
  });

  it("offers no link while the drop is still being read", () => {
    expect(targetHref(item(null))).toBeNull();
  });
});
