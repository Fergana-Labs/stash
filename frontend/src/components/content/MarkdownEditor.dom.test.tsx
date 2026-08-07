import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { Page } from "../../lib/types";
import MarkdownEditor from "./MarkdownEditor";

afterEach(() => {
  cleanup();
});

// Every construct the old rich-text editor destroyed on a round trip: a
// fenced code block (its newlines were stripped, merging two shell commands
// into one unrunnable line), a blockquote (lost its marker), and a
// frontmatter block (became a heading).
const TRICKY = `---
name: fixture
description: has everything that used to break
---

# Setup

Run this:

\`\`\`bash
npm install
npm run dev
\`\`\`

> A blockquote.

| a | b |
| - | - |
| 1 | 2 |
`;

const page: Page = {
  id: "page-1",
  owner_user_id: "user-1",
  folder_id: null,
  name: "Fixture.md",
  content_type: "markdown",
  content_markdown: TRICKY,
  content_html: "",
  html_layout: "responsive",
  content_hash: "hash-1",
  can_write: true,
  created_by: "user-1",
  updated_by: null,
  created_at: "2026-06-01T00:00:00Z",
  updated_at: "2026-06-01T00:00:00Z",
};

describe("MarkdownEditor", () => {
  it("edits the file's bytes, not a rendering of them", async () => {
    render(<MarkdownEditor file={page} onSave={vi.fn()} />);

    const area = await screen.findByRole("textbox");
    expect((area as HTMLTextAreaElement).value).toBe(TRICKY);
  });

  it("a save writes back exactly what the file had, plus what was typed", async () => {
    const onSave = vi.fn();
    render(<MarkdownEditor file={page} onSave={onSave} />);

    const area = (await screen.findByRole("textbox")) as HTMLTextAreaElement;
    fireEvent.change(area, { target: { value: `${TRICKY} x` } });

    await waitFor(() => expect(onSave).toHaveBeenCalled(), { timeout: 4000 });
    const saved = onSave.mock.calls.at(-1)?.[0] as string;
    // The code fence, its newline, the blockquote marker and the frontmatter
    // all survive — this is the regression that corrupted 193 pages' worth of
    // content one keystroke at a time.
    expect(saved).toContain("```bash\nnpm install\nnpm run dev\n```");
    expect(saved).toContain("> A blockquote.");
    expect(saved).toContain("---\nname: fixture");
    expect(saved.startsWith(TRICKY.slice(0, TRICKY.length - 1))).toBe(true);
  });

  it("opens read-only when the viewer cannot write", async () => {
    render(<MarkdownEditor file={{ ...page, can_write: false }} onSave={vi.fn()} />);

    const area = (await screen.findByRole("textbox")) as HTMLTextAreaElement;
    expect(area.readOnly).toBe(true);
    expect(screen.getByText("Read-only")).toBeInTheDocument();
  });

  it("freezes on a save conflict and says why", async () => {
    render(
      <MarkdownEditor
        file={page}
        onSave={vi.fn()}
        conflictMessage="This page changed since you loaded it — reload to get the latest version."
      />,
    );

    const area = (await screen.findByRole("textbox")) as HTMLTextAreaElement;
    expect(area.readOnly).toBe(true);
    expect(screen.getByText(/changed since you loaded it/)).toBeInTheDocument();
  });
});
