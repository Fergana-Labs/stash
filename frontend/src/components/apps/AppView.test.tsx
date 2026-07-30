import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import AppView from "./AppView";

const api = vi.hoisted(() => ({
  appFacets: vi.fn(),
  bulkEditRows: vi.fn(),
  getApp: vi.fn(),
  getTable: vi.fn(),
  installApp: vi.fn(),
  listAppRows: vi.fn(),
  listAppSkills: vi.fn(),
  listSkills: vi.fn(),
  setRowTopics: vi.fn(),
  updateTableRow: vi.fn(),
}));

vi.mock("@/lib/api", () => api);

const columns = [
  {
    id: "title",
    name: "Title",
    type: "text" as const,
    order: 0,
    required: false,
    default: null,
    options: null,
    width: 220,
  },
  {
    id: "url",
    name: "URL",
    type: "url" as const,
    order: 1,
    required: false,
    default: null,
    options: null,
    width: 240,
  },
  {
    id: "summary",
    name: "Summary",
    type: "text" as const,
    order: 2,
    required: false,
    default: null,
    options: null,
    width: 320,
  },
  {
    id: "topics",
    name: "Topics",
    type: "multiselect" as const,
    order: 3,
    required: false,
    default: null,
    options: ["AI"],
    width: 180,
  },
];

const manifest = {
  slug: "bookmarks",
  title: "Bookmarks",
  tagline: "Everything you save, summarised and sorted by topic.",
  icon: "bookmark",
  empty_state: {
    title: "Save your first bookmark",
    description: "Save something.",
    action: { label: "Learn how", href: "/extension" },
  },
  detail: {
    title: "title",
    body: "summary",
    labels: "topics",
    link: "url",
    content: "clip",
  },
  enriched_columns: ["summary", "topics"],
};

const rows = ["First", "Second", "Third"].map((title, index) => ({
  id: `row-${index + 1}`,
  table_id: "table-1",
  data: {
    title,
    url: `https://example.com/${index + 1}`,
    // The Clip cell holds an absolute app URL — possibly on a different
    // origin than the one being viewed, which is why the drawer reduces it
    // to a path rather than linking it verbatim.
    clip: `https://app.example.test/p/0000000${index + 1}-0000-4000-8000-000000000000`,
    summary: `Summary ${index + 1}`,
    topics: index === 0 ? ["AI"] : [],
  },
  row_order: index,
  created_by: "user-1",
  updated_by: null,
  created_at: "2026-07-28T00:00:00Z",
  updated_at: "2026-07-28T00:00:00Z",
}));

beforeEach(() => {
  api.getApp.mockResolvedValue({ table_id: "table-1", row_count: 3, manifest });
  api.getTable.mockResolvedValue({
    id: "table-1",
    owner_user_id: "user-1",
    folder_id: null,
    name: "Bookmarks",
    description: "",
    columns,
    views: [{ id: "recent", name: "Recent", layout: "cards" }],
    created_by: "user-1",
    updated_by: null,
    created_at: "2026-07-28T00:00:00Z",
    updated_at: "2026-07-28T00:00:00Z",
    row_count: 3,
  });
  api.listAppRows.mockResolvedValue({ rows, total: 3, has_more: false });
  api.listAppSkills.mockResolvedValue([]);
  api.listSkills.mockResolvedValue([]);
  api.appFacets.mockResolvedValue({
    total: 3,
    topics: [{ label: "AI", count: 1 }],
    untagged: 2,
    duplicates: 0,
    broken: 0,
  });
  api.updateTableRow.mockResolvedValue(rows[0]);
  api.setRowTopics.mockResolvedValue({ topics: ["AI"] });
});

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe("Bookmarks app", () => {
  it("opens as a real table without the redundant card, view, search, or tagline chrome", async () => {
    render(<AppView slug="bookmarks" />);

    await screen.findByTestId("bookmarks-table");
    expect(screen.getByRole("columnheader", { name: "Title" })).toBeTruthy();
    expect(screen.getByRole("columnheader", { name: "URL" })).toBeTruthy();
    expect(screen.getByRole("columnheader", { name: "Topics" })).toBeTruthy();
    expect(screen.getByText("https://example.com/1")).toBeTruthy();
    expect(screen.queryByTestId("bookmarks-cards")).toBeNull();
    expect(screen.queryByText("Recent")).toBeNull();
    expect(screen.queryByPlaceholderText("Search everything")).toBeNull();
    expect(screen.queryByText(manifest.tagline)).toBeNull();
  });

  it("keeps cards available without changing the table-first default", async () => {
    render(<AppView slug="bookmarks" />);

    await screen.findByTestId("bookmarks-table");
    fireEvent.click(screen.getByRole("button", { name: "Card view" }));

    expect(screen.getByTestId("bookmarks-cards")).toBeTruthy();
    expect(screen.getAllByTestId("app-card")).toHaveLength(3);
    expect(screen.queryByTestId("bookmarks-table")).toBeNull();
  });

  it("sorts the whole result set through the rows API", async () => {
    render(<AppView slug="bookmarks" />);

    const titleSort = await screen.findByRole("button", { name: "Sort by Title" });
    fireEvent.click(titleSort);
    await waitFor(() =>
      expect(api.listAppRows).toHaveBeenLastCalledWith(
        "bookmarks",
        expect.objectContaining({ sort_by: "title", sort_order: "asc" }),
      ),
    );

    fireEvent.click(titleSort);
    await waitFor(() =>
      expect(api.listAppRows).toHaveBeenLastCalledWith(
        "bookmarks",
        expect.objectContaining({ sort_by: "title", sort_order: "desc" }),
      ),
    );
  });

  it("selects a contiguous range with shift-click", async () => {
    render(<AppView slug="bookmarks" />);

    const first = await screen.findByRole("checkbox", { name: "Select First" });
    fireEvent.mouseDown(first);
    const third = screen.getByRole("checkbox", { name: "Select Third" });
    fireEvent.mouseDown(third, {
      shiftKey: true,
    });

    expect(screen.getByText("3 selected")).toBeTruthy();
  });

  it("opens an editable field drawer and saves changed row values", async () => {
    render(<AppView slug="bookmarks" />);

    fireEvent.click((await screen.findByText("First")).closest("tr")!);
    const title = screen.getByLabelText("Title");
    fireEvent.change(title, { target: { value: "Updated title" } });
    fireEvent.click(screen.getByRole("button", { name: "Save changes" }));

    await waitFor(() =>
      expect(api.updateTableRow).toHaveBeenCalledWith("table-1", "row-1", {
        title: "Updated title",
      })
    );
  });

  it("keeps generated topics visible and editable", async () => {
    render(<AppView slug="bookmarks" />);

    fireEvent.click((await screen.findByText("First")).closest("tr")!);
    expect(screen.getAllByText("AI").length).toBeGreaterThan(0);
    fireEvent.click(screen.getByTestId("add-topic"));
    fireEvent.change(screen.getByPlaceholderText("Add a topic…"), {
      target: { value: "Research" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Add" }));

    await waitFor(() =>
      expect(api.setRowTopics).toHaveBeenCalledWith("bookmarks", "row-1", [
        "AI",
        "Research",
      ])
    );
  });

  it("opens the drawer from anywhere in the row, not just the title", async () => {
    render(<AppView slug="bookmarks" />);

    // A non-title cell. The row highlights on hover across its whole width,
    // so responding only on the title reads as a broken row.
    const titleCell = (await screen.findByText("First")).closest("td")!;
    const otherCell = titleCell.nextElementSibling as HTMLElement;
    fireEvent.click(otherCell);

    expect(await screen.findByTestId("app-detail")).toBeTruthy();
  });

  it("does not open the drawer when ticking the row's checkbox", async () => {
    render(<AppView slug="bookmarks" />);

    const row = (await screen.findByText("First")).closest("tr")!;
    fireEvent.mouseDown(row.querySelector('input[type="checkbox"]')!);

    expect(screen.getByText("1 selected")).toBeTruthy();
    expect(screen.queryByTestId("app-detail")).toBeNull();
  });

  it("keeps links to the saved copy and the original in the drawer", async () => {
    render(<AppView slug="bookmarks" />);

    fireEvent.click((await screen.findByText("First")).closest("tr")!);

    // The two things a bookmark is for. A drawer that can edit fields but
    // can't reach either is a spreadsheet cell with extra steps.
    const links = within(screen.getByTestId("detail-links")).getAllByRole("link");
    const hrefs = links.map((link) => link.getAttribute("href"));
    expect(hrefs).toContain("https://example.com/1");
    expect(hrefs.some((href) => href?.startsWith("/p/"))).toBe(true);
    expect(links.every((link) => link.getAttribute("target") === "_blank")).toBe(true);
  });
});
