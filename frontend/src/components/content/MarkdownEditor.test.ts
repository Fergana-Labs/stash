import { describe, expect, it } from "vitest";

import {
  extractCommentIdsFromMarkdown,
  markdownToInitialJSON,
  serializeMarkdown,
} from "./MarkdownEditor";

// Round-trip = parse markdown → ProseMirror JSON → re-serialize → expect
// the markdown to come back recognizably the same. This catches regressions
// where the `<span data-comment-id>` wrapper gets dropped or where inner
// markdown marks (bold/italic/link) inside a comment get corrupted on save.

describe("MarkdownEditor markdown round-trip", () => {
  it("preserves a comment span wrapping plain text", () => {
    const md = 'Here is <span data-comment-id="abc-1">commented text</span> in a paragraph.\n';
    const doc = markdownToInitialJSON(md);
    const out = serializeMarkdown(doc, md);
    expect(out).toContain('<span data-comment-id="abc-1">commented text</span>');
  });

  it("preserves a comment span wrapping a bold run", () => {
    const md = '<span data-comment-id="abc-2">**important**</span>\n';
    const doc = markdownToInitialJSON(md);
    const out = serializeMarkdown(doc, md);
    expect(out).toContain('<span data-comment-id="abc-2">**important**</span>');
  });

  it("preserves a comment span containing bold + italic + a link", () => {
    const md =
      '<span data-comment-id="abc-3">read **bold** and *italic* and [link](https://x.com)</span>\n';
    const doc = markdownToInitialJSON(md);
    const out = serializeMarkdown(doc, md);
    expect(out).toContain('data-comment-id="abc-3"');
    expect(out).toContain("**bold**");
    expect(out).toContain("*italic*");
    expect(out).toContain("[link](https://x.com)");
  });

  it("places the comment wrapper outside (not inside) bold", () => {
    const md = '<span data-comment-id="abc-4">**hello**</span>\n';
    const doc = markdownToInitialJSON(md);
    const out = serializeMarkdown(doc, md);
    expect(out.indexOf("<span")).toBeLessThan(out.indexOf("**"));
  });

  it("keeps neighboring plain text intact around a comment span", () => {
    const md = 'before <span data-comment-id="abc-5">middle</span> after\n';
    const doc = markdownToInitialJSON(md);
    const out = serializeMarkdown(doc, md);
    expect(out).toContain("before ");
    expect(out).toContain('<span data-comment-id="abc-5">middle</span>');
    expect(out).toContain(" after");
  });

  it("extracts every distinct data-comment-id present in the content", () => {
    const md =
      'a <span data-comment-id="id-1">x</span> b <span data-comment-id="id-2">y</span> c <span data-comment-id="id-1">z</span>\n';
    expect(extractCommentIdsFromMarkdown(md).sort()).toEqual(["id-1", "id-2"]);
  });

  it("returns no ids on content without comment spans", () => {
    expect(extractCommentIdsFromMarkdown("plain **bold** *italic* text")).toEqual([]);
  });

  it("preserves file download image URLs", () => {
    const md =
      "![diagram](/api/v1/me/files/file-1/download)\n";
    const doc = markdownToInitialJSON(md);
    const out = serializeMarkdown(doc, md);
    expect(out).toBe("![diagram](/api/v1/me/files/file-1/download)");
  });
});
