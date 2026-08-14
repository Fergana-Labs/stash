import { describe, expect, it } from "vitest";
import { firstUrlFromDrag, isLinkDrop } from "./hopper";

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

describe("firstUrlFromDrag", () => {
  it("takes the first real URL out of a uri-list", () => {
    expect(firstUrlFromDrag("https://example.com/a\r\nhttps://example.com/b\r\n")).toBe(
      "https://example.com/a",
    );
  });

  it("ignores the comment lines the format allows", () => {
    expect(firstUrlFromDrag("# a comment\r\nhttps://example.com/a")).toBe("https://example.com/a");
  });

  it("has nothing to offer for an empty list", () => {
    expect(firstUrlFromDrag("\r\n")).toBe("");
  });
});
