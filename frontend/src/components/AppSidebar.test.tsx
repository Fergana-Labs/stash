import { cleanup, render, screen, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import AppSidebar from "./AppSidebar";
import { resetStashNavigationCache } from "../lib/stashNavigationCache";
import {
  getStashSpine,
  listMyWorkspaces,
  listPublicWorkspaces,
} from "../lib/api";

const nav = vi.hoisted(() => ({
  pathname: "/",
  push: vi.fn(),
}));

vi.mock("next/navigation", () => ({
  usePathname: () => nav.pathname,
  useRouter: () => ({ push: nav.push }),
}));

vi.mock("next/link", () => ({
  default: ({
    href,
    children,
    ...props
  }: {
    href: string;
    children: ReactNode;
  }) => (
    <a href={href} {...props}>
      {children}
    </a>
  ),
}));

vi.mock("../lib/api", () => ({
  getFolderContents: vi.fn(),
  getStashSpine: vi.fn(),
  listMyWorkspaces: vi.fn(),
  listPublicWorkspaces: vi.fn(),
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
  is_public: false,
  created_at: "2026-05-11T00:00:00Z",
  updated_at: "2026-05-11T00:00:00Z",
  member_count: 1,
};

const sharedWorkspace = {
  ...workspace,
  id: "ws-2",
  name: "Shared Stash",
  creator_id: "user-2",
  invite_code: "shared",
};

const emptySpine = {
  sessions: [],
  wiki: {
    folders: [],
    pages: [],
    files: [],
  },
};

function detailsFor(label: string): HTMLDetailsElement {
  const details = screen.getByText(label).closest("details");
  if (!details) throw new Error(`No details element for ${label}`);
  return details as HTMLDetailsElement;
}

describe("AppSidebar tree expansion", () => {
  beforeEach(() => {
    resetStashNavigationCache();
    localStorage.clear();
    nav.pathname = "/";
    nav.push.mockClear();
    vi.clearAllMocks();
    vi.mocked(listMyWorkspaces).mockResolvedValue({ workspaces: [workspace] });
    vi.mocked(listPublicWorkspaces).mockResolvedValue({ workspaces: [] });
    vi.mocked(getStashSpine).mockResolvedValue(emptySpine);
  });

  afterEach(() => {
    cleanup();
  });

  it("starts stashes and their top-level sections collapsed", async () => {
    render(<AppSidebar user={user} onCmdkOpen={vi.fn()} />);

    await screen.findByText("Demo Stash");

    expect(detailsFor("Demo Stash")).not.toHaveAttribute("open");
    expect(detailsFor("Sessions")).not.toHaveAttribute("open");
    expect(detailsFor("Wiki")).not.toHaveAttribute("open");
    expect(getStashSpine).not.toHaveBeenCalled();
  });

  it("splits owned and shared memberships without reading the public catalog", async () => {
    vi.mocked(listMyWorkspaces).mockResolvedValue({
      workspaces: [workspace, sharedWorkspace],
    });

    render(<AppSidebar user={user} onCmdkOpen={vi.fn()} />);

    await screen.findByText("Shared Stash");
    await screen.findByText("Demo Stash");

    const sidebarText = document.body.textContent ?? "";
    expect(sidebarText.indexOf("SHARED WITH ME")).toBeLessThan(
      sidebarText.indexOf("Shared Stash")
    );
    expect(sidebarText.indexOf("Shared Stash")).toBeLessThan(
      sidebarText.indexOf("MY STASHES")
    );
    expect(sidebarText.indexOf("MY STASHES")).toBeLessThan(
      sidebarText.indexOf("Demo Stash")
    );
    expect(screen.getAllByText("Shared Stash")).toHaveLength(1);
    expect(listPublicWorkspaces).not.toHaveBeenCalled();
  });

  it("restores explicit expanded state from localStorage", async () => {
    localStorage.setItem("stash_sidebar_open_stashes", "ws-1");
    localStorage.setItem("stash_sidebar_open_sections", "ws-1:sessions");

    render(<AppSidebar user={user} onCmdkOpen={vi.fn()} />);

    await screen.findByText("Demo Stash");

    await waitFor(() => expect(detailsFor("Demo Stash")).toHaveAttribute("open"));
    expect(detailsFor("Sessions")).toHaveAttribute("open");
    expect(detailsFor("Wiki")).not.toHaveAttribute("open");
    expect(getStashSpine).toHaveBeenCalledWith("ws-1");
  });

  it("keeps the stash landing route collapsed without saved state", async () => {
    nav.pathname = "/stashes/ws-1";

    render(<AppSidebar user={user} onCmdkOpen={vi.fn()} />);

    await screen.findByText("Demo Stash");

    expect(detailsFor("Demo Stash")).not.toHaveAttribute("open");
    expect(detailsFor("Sessions")).not.toHaveAttribute("open");
    expect(detailsFor("Wiki")).not.toHaveAttribute("open");
    expect(getStashSpine).not.toHaveBeenCalled();
  });

  it("opens the relevant tree branch for deep links only", async () => {
    nav.pathname = "/stashes/ws-1/p/page-1";

    render(<AppSidebar user={user} onCmdkOpen={vi.fn()} />);

    await screen.findByText("Demo Stash");

    await waitFor(() => expect(detailsFor("Demo Stash")).toHaveAttribute("open"));
    expect(detailsFor("Sessions")).not.toHaveAttribute("open");
    expect(detailsFor("Wiki")).toHaveAttribute("open");
    expect(localStorage.getItem("stash_sidebar_open_stashes")).toBeNull();
    expect(localStorage.getItem("stash_sidebar_open_sections")).toBeNull();
  });

  it("reuses loaded workspace and spine data after a remount", async () => {
    nav.pathname = "/stashes/ws-1/p/page-1";

    const first = render(<AppSidebar user={user} onCmdkOpen={vi.fn()} />);
    await screen.findByText("Demo Stash");
    await waitFor(() => expect(getStashSpine).toHaveBeenCalledWith("ws-1"));
    expect(listMyWorkspaces).toHaveBeenCalledTimes(1);
    expect(getStashSpine).toHaveBeenCalledTimes(1);

    first.unmount();
    vi.clearAllMocks();

    render(<AppSidebar user={user} onCmdkOpen={vi.fn()} />);

    await screen.findByText("Demo Stash");
    expect(listMyWorkspaces).not.toHaveBeenCalled();
    expect(getStashSpine).not.toHaveBeenCalled();
    expect(detailsFor("Demo Stash")).toHaveAttribute("open");
  });
});
