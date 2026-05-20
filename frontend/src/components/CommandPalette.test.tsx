import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import type { MouseEvent, ReactNode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import CommandPalette from "./CommandPalette";
import {
  getCachedWorkspaceSidebar,
  readCachedWorkspaceSidebar,
} from "../lib/stashNavigationCache";
import { semanticSearchPages } from "../lib/api";

const searchPlaceholder = "Search Stash or jump to a page, session, or file...";

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

vi.mock("../lib/stashNavigationCache", () => ({
  readCachedWorkspaceSidebar: vi.fn(),
  getCachedWorkspaceSidebar: vi.fn(),
}));

vi.mock("../lib/api", () => ({
  semanticSearchPages: vi.fn(),
}));

const sidebar = {
  sessions: [],
  stashes: [],
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

    expect(router.push).toHaveBeenCalledWith("/workspaces/ws-1/p/page-1");
  });
});
