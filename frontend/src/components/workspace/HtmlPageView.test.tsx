import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import HtmlPageView, { stripHtmlPageRuntimeState } from "./HtmlPageView";

afterEach(cleanup);

const pollutedHtml = `<!doctype html>
<html>
  <head>
    <style id="__stash_comments_css__">.old-blue-line{outline:2px dashed blue}</style>
    <script id="__stash_resize_script__">window.oldResizeBootstrap = true;</script>
  </head>
  <body contenteditable="true" spellcheck="true">
    <main>Public page content</main>
  </body>
</html>`;

describe("stripHtmlPageRuntimeState", () => {
  it("removes edit-only body attributes and stale bootstrap tags", () => {
    const cleaned = stripHtmlPageRuntimeState(pollutedHtml);

    expect(cleaned).toContain("<body>");
    expect(cleaned).toContain("Public page content");
    expect(cleaned).not.toMatch(/<body\b[^>]*\bcontenteditable/i);
    expect(cleaned).not.toMatch(/<body\b[^>]*\bspellcheck/i);
    expect(cleaned).not.toContain("old-blue-line");
    expect(cleaned).not.toContain("oldResizeBootstrap");
  });
});

describe("HtmlPageView", () => {
  it("builds read-only iframe HTML without persisted edit mode state", () => {
    render(<HtmlPageView html={pollutedHtml} title="Public proposal" />);

    const iframe = screen.getByTitle("Public proposal");
    const srcDoc = iframe.getAttribute("srcdoc") ?? "";

    expect(srcDoc).toContain("Public page content");
    expect(srcDoc).not.toMatch(/<body\b[^>]*\bcontenteditable/i);
    expect(srcDoc).not.toMatch(/<body\b[^>]*\bspellcheck/i);
    expect(srcDoc).not.toContain("old-blue-line");
    expect(srcDoc).not.toContain("oldResizeBootstrap");
  });
});
