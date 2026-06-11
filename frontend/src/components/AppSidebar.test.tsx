import { cleanup, render, screen, waitFor } from "@testing-library/react";
import type { MouseEvent, ReactNode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import AppSidebar from "./AppSidebar";
import { resetStashNavigationCache } from "../lib/stashNavigationCache";
import {
  getWorkspacePins,
  getWorkspaceSidebar,
  listMyWorkspaces,
  listWorkspaceSources,
} from "../lib/api";

const nav = vi.hoisted(() => ({
  pathname: "/",
}));

vi.mock("next/navigation", () => ({
  usePathname: () => nav.pathname,
  useRouter: () => ({ push: vi.fn() }),
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

vi.mock("../lib/api", () => ({
  getWorkspaceSidebar: vi.fn(),
  listMyWorkspaces: vi.fn(),
  getWorkspacePins: vi.fn(),
  setWorkspacePins: vi.fn(),
  getWorkspaceRecents: vi.fn(),
  recordWorkspaceRecent: vi.fn(),
  listWorkspaceSources: vi.fn(),
}));

const user = {
  id: "user-1",
  name: "Henry",
  display_name: "Henry",
  description: "",
  created_at: "2026-05-11T00:00:00Z",
  last_seen: "2026-05-11T00:00:00Z",
};

const workspace = {
  id: "ws-1",
  name: "Demo Stash",
  description: "",
  creator_id: "user-1",
  invite_code: "invite",
  created_at: "2026-05-11T00:00:00Z",
  updated_at: "2026-05-11T00:00:00Z",
  member_count: 1,
};

function navLink(label: string): HTMLAnchorElement {
  const link = screen.getByText(label).closest("a");
  if (!link) throw new Error(`No link for ${label}`);
  return link as HTMLAnchorElement;
}

beforeEach(() => {
  nav.pathname = "/workspaces/ws-1";
  localStorage.clear();
  resetStashNavigationCache();
  vi.mocked(listMyWorkspaces).mockResolvedValue({ workspaces: [workspace] });
  vi.mocked(getWorkspaceSidebar).mockResolvedValue({
    sessions: [],
    files: { folders: [], pages: [], files: [] },
    cartridges: [],
  });
  vi.mocked(getWorkspacePins).mockResolvedValue({ cartridges: [], sessions: [], files: [] });
  vi.mocked(listWorkspaceSources).mockResolvedValue([]);
});

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe("AppSidebar workspace nav", () => {
  it("links Cartridges, Sessions, and Drive straight to their list pages", async () => {
    render(<AppSidebar user={user} />);

    await waitFor(() => expect(navLink("Cartridges")).toBeTruthy());

    expect(navLink("Cartridges").getAttribute("href")).toBe("/workspaces/ws-1/cartridges");
    expect(navLink("Agent Sessions").getAttribute("href")).toBe("/workspaces/ws-1/sessions");
    expect(navLink("Drive").getAttribute("href")).toBe("/workspaces/ws-1/files");
    expect(navLink("Trash").getAttribute("href")).toBe("/workspaces/ws-1/trash");
  });

  it("does not render native <details> trees for the sections", async () => {
    const { container } = render(<AppSidebar user={user} />);

    await waitFor(() => expect(navLink("Drive")).toBeTruthy());

    expect(container.querySelector("details")).toBeNull();
  });

  it("marks the Drive section active when viewing a file route", async () => {
    nav.pathname = "/workspaces/ws-1/folders/folder-1";
    render(<AppSidebar user={user} />);

    await waitFor(() => expect(navLink("Drive")).toBeTruthy());

    expect(navLink("Drive").className).toContain("color-brand-800");
    expect(navLink("Agent Sessions").className).not.toContain("color-brand-800");
  });
});
