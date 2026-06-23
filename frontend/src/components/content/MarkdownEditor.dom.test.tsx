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
  created_by: "user-1",
  updated_by: null,
  created_at: "2026-06-01T00:00:00Z",
  updated_at: "2026-06-01T00:00:00Z",
};

describe("MarkdownEditor DOM", () => {
  it("disables browser spellcheck on the editable surface", async () => {
    render(
      <MarkdownEditor
        file={page}
        onSave={vi.fn()}
        collaborationUser={{ id: "user-1", name: "Test User" }}
      />,
    );

    await waitFor(() => {
      expect(document.querySelector(".ProseMirror")).toHaveAttribute(
        "spellcheck",
        "false",
      );
    });
  });
});
