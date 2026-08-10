// The /files lens must rest as bare `ls` output, bloom the hovered mount one
// level, open folders as the cursor touches them, keep big directories behind
// "+N more", and disclose rows the API withheld — the behaviors that make it
// a whole-stash view that never overwhelms.
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import FilesOverview from "./FilesOverview";
import {
  getMemoryFolder,
  getMeOverview,
  getSidebar,
  getSourcesTree,
  listSkills,
  listTables,
} from "@/lib/api";

vi.mock("@/lib/api", () => ({
  getSidebar: vi.fn(),
  listTables: vi.fn(),
  listSkills: vi.fn(),
  getMeOverview: vi.fn(),
  getMemoryFolder: vi.fn(),
  getSourcesTree: vi.fn(),
}));

const MEMORY_ID = "memory-folder";

function sidebar() {
  return {
    sessions: [
      {
        id: "s1", session_id: "sess-1", title: "Fix the onboarding wizard",
        linear_tickets: [], user_name: "henry", agent_name: "claude",
        size_bytes: 10, last_at: new Date().toISOString(), updated_at: new Date().toISOString(),
      },
    ],
    files: {
      folders: [
        { id: "root-1", name: "Research", parent_folder_id: null, page_count: 12, file_count: 0 },
        { id: MEMORY_ID, name: "Memory", parent_folder_id: null, page_count: 0, file_count: 0 },
      ],
      // 12 pages inside Research: enough to trip the per-directory cap.
      pages: Array.from({ length: 12 }, (_, i) => ({
        id: `p${i}`, name: `Page ${String(i).padStart(2, "0")}`,
        content_type: "markdown" as const, folder_id: "root-1",
      })),
      files: [],
    },
    skills: [],
  };
}

beforeEach(() => {
  vi.mocked(getSidebar).mockResolvedValue(sidebar());
  vi.mocked(listTables).mockResolvedValue({ tables: [] });
  vi.mocked(listSkills).mockResolvedValue([]);
  vi.mocked(getMeOverview).mockResolvedValue({ pages: 14, files: 0, sessions: 5 });
  vi.mocked(getMemoryFolder).mockResolvedValue({
    id: MEMORY_ID, name: "Memory", owner_user_id: "u1", parent_folder_id: null,
    created_by: "u1", created_at: "2026-01-01T00:00:00Z", updated_at: "2026-01-01T00:00:00Z",
  });
  vi.mocked(getSourcesTree).mockResolvedValue([
    // Alphabetically first but empty — must sort AFTER github, which has content.
    {
      source: "asana", type: "provider", provider: "asana", display_name: "asana",
      members: [{ handle: "src-2", display_name: "Roadmap" }],
      sync_status: "idle", last_synced_at: null,
      tree: [],
    },
    {
      source: "github", type: "provider", provider: "github", display_name: "github",
      members: [{ handle: "src-1", display_name: "stash" }],
      sync_status: "idle", last_synced_at: null,
      tree: [
        {
          name: "docs", kind: "folder",
          children: [
            { name: "api.md", kind: "file", path: "docs/api.md" },
            { name: "", kind: "truncated", hidden: 40 },
          ],
        },
      ],
    },
  ]);
});

afterEach(cleanup);

// React derives onMouseEnter from mouseover, so mouseOver is the reliable
// way to hover a row in jsdom.
function hover(text: string) {
  fireEvent.mouseOver(screen.getByText(text));
}

describe("FilesOverview", () => {
  it("rests as bare ls output: every mount name, no tree", async () => {
    render(<FilesOverview />);
    await waitFor(() => expect(screen.getByText("/sources")).toBeTruthy());
    for (const path of ["/files", "/sessions", "/memory", "/skills", "/sources"]) {
      expect(screen.getByText(path)).toBeTruthy();
    }
    expect(screen.queryByText("Research")).toBeNull();
    // Providers live INSIDE /sources, exactly like the real VFS.
    expect(screen.queryByText("github")).toBeNull();
    // Memory renders as its own mount, not a folder row under /files.
    expect(screen.queryByText("Memory")).toBeNull();
  });

  it("blooms the hovered mount one level, and opens folders on hover", async () => {
    render(<FilesOverview />);
    await waitFor(() => expect(screen.getByText("/files")).toBeTruthy());

    hover("/files");
    expect(screen.getByText("Research")).toBeTruthy();
    // The mount blooms one level: Research itself shows, its contents don't.
    expect(screen.queryByText("Page 00")).toBeNull();

    hover("Research");
    expect(screen.getByText("Page 00")).toBeTruthy();

    // Moving the lens to another mount swaps the bloom and forgets open dirs.
    hover("/sessions");
    expect(screen.queryByText("Research")).toBeNull();
    expect(screen.getByText("Fix the onboarding wizard")).toBeTruthy();
    hover("/files");
    expect(screen.queryByText("Page 00")).toBeNull();
  });

  it("dir rows with an href navigate; their chevron still toggles", async () => {
    render(<FilesOverview />);
    await waitFor(() => expect(screen.getByText("/sources")).toBeTruthy());

    // A provider is a real Stash object — its row is a link to the
    // integration page, not a click-swallowing toggle button. The section
    // stamp keeps the VFS docked instead of teleporting to Tools.
    hover("/sources");
    const github = screen.getByRole("link", { name: /github/ });
    expect(github.getAttribute("href")).toBe("/integrations/github?section=files");

    // Folders under /files link to their explorer page the same way.
    hover("/files");
    const research = screen.getByRole("link", { name: /Research/ });
    expect(research.getAttribute("href")).toBe("/folders/root-1");

    // The chevron keeps expand/collapse duty without following the link.
    hover("Research");
    expect(screen.getByText("Page 00")).toBeTruthy();
    fireEvent.click(research.querySelector('[aria-label="collapse"]')!);
    expect(screen.queryByText("Page 00")).toBeNull();
  });

  it("depth gauge peeks every mount open, and springs back flat on leave", async () => {
    render(<FilesOverview />);
    await waitFor(() => expect(screen.getByText("/files")).toBeTruthy());

    const gauge = screen.getByRole("slider", { name: "tree depth" });
    // jsdom has no layout, so pin the gauge's rect for the sweep math.
    Object.defineProperty(gauge, "getBoundingClientRect", {
      value: () => ({ left: 0, top: 0, right: 200, bottom: 20, width: 200, height: 20, x: 0, y: 0, toJSON: () => ({}) }),
    });

    // 90% across = full depth: github's docs/ folder is three levels down.
    fireEvent.mouseMove(gauge, { clientX: 180 });
    expect(screen.getByText("Page 00")).toBeTruthy();
    expect(screen.getByText("Fix the onboarding wizard")).toBeTruthy();
    expect(screen.getByText("api.md")).toBeTruthy();

    // Leaving the gauge is not a mode change — everything snaps back flat.
    fireEvent.mouseLeave(gauge);
    expect(screen.queryByText("Research")).toBeNull();
    expect(screen.queryByText("api.md")).toBeNull();

    // Clicking pins the depth: it survives leaving the gauge.
    fireEvent.mouseMove(gauge, { clientX: 120 });
    fireEvent.click(gauge, { clientX: 120 });
    fireEvent.mouseLeave(gauge);
    expect(screen.getByText("Page 00")).toBeTruthy();

    // Clicking the same depth again unpins — back to a peek.
    fireEvent.click(gauge, { clientX: 120 });
    fireEvent.mouseLeave(gauge);
    expect(screen.queryByText("Research")).toBeNull();
  });

  it("caps big directories behind a +N more toggle", async () => {
    render(<FilesOverview />);
    await waitFor(() => expect(screen.getByText("/files")).toBeTruthy());
    hover("/files");
    hover("Research");
    expect(screen.getByText("Page 00")).toBeTruthy();
    expect(screen.queryByText("Page 11")).toBeNull();
    fireEvent.click(screen.getByText("… +2 more"));
    expect(screen.getByText("Page 11")).toBeTruthy();
  });

  it("nests providers under /sources and discloses rows the API withheld", async () => {
    render(<FilesOverview />);
    await waitFor(() => expect(screen.getByText("/sources")).toBeTruthy());
    hover("/sources");
    expect(screen.getByText("github")).toBeTruthy();
    expect(screen.queryByText("docs")).toBeNull();
    // Synced providers sort ahead of empty ones, despite the alphabet.
    const order = document.body.textContent!;
    expect(order.indexOf("github")).toBeLessThan(order.indexOf("asana"));
    hover("github");
    expect(screen.getByText("docs")).toBeTruthy();
    expect(screen.queryByText("api.md")).toBeNull();
    hover("docs");
    expect(screen.getByText("api.md")).toBeTruthy();
    expect(screen.getByText(/40 more synced/)).toBeTruthy();
  });
});
