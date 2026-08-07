import { cleanup, render, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { Page } from "../../lib/types";
import MarkdownEditor from "./MarkdownEditor";

afterEach(() => {
  cleanup();
});

const page: Page = {
  id: "page-1",
  owner_user_id: "user-1",
  folder_id: null,
  name: "Skill ICP - Rachel",
  content_type: "markdown",
  content_markdown: "Rachel Wolan uses Skill at Webflow and biglabs.",
  content_html: "",
  html_layout: "responsive",
  content_hash: "hash-1",
  can_write: true,
  created_by: "user-1",
  updated_by: null,
  created_at: "2026-06-01T00:00:00Z",
  updated_at: "2026-06-01T00:00:00Z",
};

describe("MarkdownEditor DOM", () => {
  it("disables browser spellcheck on the editable surface", async () => {
    render(<MarkdownEditor file={page} onSave={vi.fn()} />);

    await waitFor(() => {
      expect(document.querySelector(".ProseMirror")).toHaveAttribute(
        "spellcheck",
        "false",
      );
    });
  });

  it("renders the stored markdown body without a collab round trip", async () => {
    render(<MarkdownEditor file={page} onSave={vi.fn()} />);

    await waitFor(() => {
      expect(document.querySelector(".ProseMirror")?.textContent).toContain(
        "Rachel Wolan uses Skill at Webflow",
      );
    });
  });

  it("shows frontmatter read-only and keeps it out of the editable body", async () => {
    const withFm: Page = {
      ...page,
      id: "page-2",
      content_markdown: "---\nname: rachel-icp\ndescription: ICP notes\n---\n\n# Body here\n",
    };
    render(<MarkdownEditor file={withFm} onSave={vi.fn()} />);

    await waitFor(() => {
      expect(document.querySelector(".ProseMirror")?.textContent).toContain("Body here");
    });
    // The metadata is visible in the strip…
    expect(document.body.textContent).toContain("name: rachel-icp");
    // …but not inside the editable document, where it used to get parsed
    // into a heading and destroyed on save.
    expect(document.querySelector(".ProseMirror")?.textContent).not.toContain("name: rachel-icp");
  });

  it("opens read-only when the viewer cannot write", async () => {
    render(<MarkdownEditor file={{ ...page, can_write: false }} onSave={vi.fn()} />);

    await waitFor(() => {
      expect(document.querySelector(".ProseMirror")).toHaveAttribute(
        "contenteditable",
        "false",
      );
    });
  });
});
