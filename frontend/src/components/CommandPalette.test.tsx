import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import type { MouseEvent, ReactNode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import CommandPalette from "./CommandPalette";
import {
  getCachedWorkspaceSidebar,
  readCachedWorkspaceSidebar,
} from "../lib/skillNavigationCache";
import { listAllTables, semanticSearchPages } from "../lib/api";

const searchPlaceholder = "Search Skill or jump to a page, session, file, or table...";

const router = vi.hoisted(() => ({
  push: vi.fn(),
}));

vi.mock("next/navigation", () => ({
  useRouter: () => router,
}));

vi.mock("next/link", () => ({
  default: ({
    href,
    children,
    onClick,
    ...props
  }: {
    href: string;
    children: ReactNode;
    onClick?: (event: MouseEvent<HTMLAnchorElement>) => void;
  }) => (
    <a
      href={href}
      {...props}
      onClick={(event) => {
        event.preventDefault();
        onClick?.(event);
      }}
    >
      {children}
    </a>
  ),
}));

vi.mock("../lib/skillNavigationCache", () => ({
  readCachedWorkspaceSidebar: vi.fn(),
  getCachedWorkspaceSidebar: vi.fn(),
}));

vi.mock("../lib/api", () => ({
  listAllTables: vi.fn(),
  semanticSearchPages: vi.fn(),
}));

const sidebar = {
  sessions: [],
  skills: [],
  files: {
    folders: [],
    pages: [
      {
        id: "page-1",
        name: "Launch Roadmap.md",
        content_type: "markdown" as const,
        folder_id: null,
      },
    ],
    files: [],
  },
};

function renderPalette() {
  return render(
    <CommandPalette
      open
      onClose={vi.fn()}
      anchorRef={{ current: null }}
      workspaceId="ws-1"
      workspaceName="Demo Workspace"
      searchScope={{
        kind: "workspace",
        label: "Demo Workspace",
        detail: "Search this workspace",
        params: { workspace: "ws-1" },
      }}
    />
  );
}

describe("CommandPalette search", () => {
  beforeEach(() => {
    router.push.mockClear();
    vi.clearAllMocks();
    vi.mocked(readCachedWorkspaceSidebar).mockReturnValue(sidebar);
    vi.mocked(getCachedWorkspaceSidebar).mockResolvedValue(sidebar);
    vi.mocked(listAllTables).mockResolvedValue({ tables: [] });
    vi.mocked(semanticSearchPages).mockResolvedValue([]);
  });

  afterEach(() => {
    cleanup();
  });

  it("opens full-page search when Enter is pressed from the search input", () => {
    renderPalette();

    fireEvent.change(screen.getByPlaceholderText(searchPlaceholder), {
      target: { value: "roadmap" },
    });
    fireEvent.keyDown(window, { key: "Enter" });

    expect(router.push).toHaveBeenCalledWith("/search?workspace=ws-1&q=roadmap");
  });

  it("keeps jump results available after the full-page search action", () => {
    renderPalette();

    fireEvent.change(screen.getByPlaceholderText(searchPlaceholder), {
      target: { value: "roadmap" },
    });
    fireEvent.keyDown(window, { key: "ArrowDown" });
    fireEvent.keyDown(window, { key: "Enter" });

    expect(router.push).toHaveBeenCalledWith("/p/page-1");
  });

  it("finds matching tables in the active workspace", async () => {
    vi.mocked(listAllTables).mockResolvedValue({
      tables: [
        {
          id: "table-1",
          workspace_id: "ws-1",
          folder_id: null,
          workspace_name: "Demo Workspace",
          name: "Hiring Outreach CRM",
          description: "",
          columns: [],
          views: [],
          created_by: "user-1",
          updated_by: null,
          created_at: "2026-01-01T00:00:00Z",
          updated_at: "2026-01-02T00:00:00Z",
          row_count: 177,
        },
      ],
    });
    renderPalette();

    fireEvent.change(screen.getByPlaceholderText(searchPlaceholder), {
      target: { value: "hiring outreach" },
    });

    expect(await screen.findByText("Hiring Outreach CRM")).toBeInTheDocument();

    // The window keydown listener re-subscribes in a passive effect after the
    // table result lands; on a loaded runner findByText can resolve before that
    // effect flushes, leaving ArrowDown bound to the stale one-result list.
    await act(async () => {});

    fireEvent.keyDown(window, { key: "ArrowDown" });
    fireEvent.keyDown(window, { key: "Enter" });

    expect(router.push).toHaveBeenCalledWith("/tables/table-1");
  });
});
