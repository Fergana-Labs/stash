import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import AppSidebar from "./AppSidebar";
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

describe("AppSidebar tree expansion", () => {
  beforeEach(() => {
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
    render(<AppSidebar user={user} collapsed={false} onCmdkOpen={vi.fn()} />);

    await screen.findByText("Demo Stash");

    expect(screen.getByLabelText("Expand stash")).toBeInTheDocument();
    expect(screen.queryByText("Sessions")).not.toBeInTheDocument();
    expect(screen.queryByText("Wiki")).not.toBeInTheDocument();
    expect(getStashSpine).not.toHaveBeenCalled();
  });

  it("splits owned and shared memberships without reading the public catalog", async () => {
    vi.mocked(listMyWorkspaces).mockResolvedValue({
      workspaces: [workspace, sharedWorkspace],
    });

    render(<AppSidebar user={user} collapsed={false} onCmdkOpen={vi.fn()} />);

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

    render(<AppSidebar user={user} collapsed={false} onCmdkOpen={vi.fn()} />);

    await screen.findByText("Demo Stash");

    await waitFor(() => expect(screen.getByLabelText("Collapse stash")).toBeInTheDocument());
    expect(screen.getByLabelText("Collapse sessions")).toBeInTheDocument();
    expect(screen.getByLabelText("Expand wiki")).toBeInTheDocument();
    expect(getStashSpine).toHaveBeenCalledWith("ws-1");
  });

  it("gives section rows separate navigation and disclosure targets", async () => {
    localStorage.setItem("stash_sidebar_open_stashes", "ws-1");

    render(<AppSidebar user={user} collapsed={false} onCmdkOpen={vi.fn()} />);

    await screen.findByText("Demo Stash");
    const sessionsLink = await screen.findByRole("link", { name: /Sessions/ });
    expect(sessionsLink).toHaveAttribute("href", "/stashes/ws-1/sessions");

    fireEvent.click(screen.getByLabelText("Expand sessions"));

    expect(screen.getByLabelText("Collapse sessions")).toBeInTheDocument();
    expect(sessionsLink).toHaveAttribute("href", "/stashes/ws-1/sessions");
  });

  it("shows generated session titles with compact timestamps", async () => {
    const lastAt = "2026-05-11T18:24:00Z";
    const timestamp = new Intl.DateTimeFormat(undefined, {
      month: "short",
      day: "numeric",
      hour: "numeric",
      minute: "2-digit",
    }).format(new Date(lastAt));
    vi.mocked(getStashSpine).mockResolvedValue({
      ...emptySpine,
      sessions: [
        {
          session_id: "agent-1",
          title: "Refine Sidebar Session Titles",
          agent_name: "codex",
          event_count: 12,
          size_bytes: 1024,
          last_at: lastAt,
          updated_at: lastAt,
        },
      ],
    });
    localStorage.setItem("stash_sidebar_open_stashes", "ws-1");
    localStorage.setItem("stash_sidebar_open_sections", "ws-1:sessions");

    render(<AppSidebar user={user} collapsed={false} onCmdkOpen={vi.fn()} />);

    const sessionLink = await screen.findByRole("link", {
      name: /Refine Sidebar Session Titles/,
    });

    expect(sessionLink).toHaveAttribute("href", "/stashes/ws-1/sessions/agent-1");
    expect(sessionLink).toHaveAttribute("title", `Refine Sidebar Session Titles - ${timestamp}`);
    expect(screen.getByText(timestamp)).toBeInTheDocument();
  });

  it("keeps the stash landing route collapsed without saved state", async () => {
    nav.pathname = "/stashes/ws-1";

    render(<AppSidebar user={user} collapsed={false} onCmdkOpen={vi.fn()} />);

    await screen.findByText("Demo Stash");

    expect(screen.getByLabelText("Expand stash")).toBeInTheDocument();
    expect(screen.queryByText("Sessions")).not.toBeInTheDocument();
    expect(screen.queryByText("Wiki")).not.toBeInTheDocument();
    expect(getStashSpine).not.toHaveBeenCalled();
  });

  it("opens the relevant tree branch for deep links only", async () => {
    nav.pathname = "/stashes/ws-1/p/page-1";

    render(<AppSidebar user={user} collapsed={false} onCmdkOpen={vi.fn()} />);

    await screen.findByText("Demo Stash");

    await waitFor(() => expect(screen.getByLabelText("Collapse stash")).toBeInTheDocument());
    expect(screen.getByLabelText("Expand sessions")).toBeInTheDocument();
    expect(screen.getByLabelText("Collapse wiki")).toBeInTheDocument();
    expect(localStorage.getItem("stash_sidebar_open_stashes")).toBeNull();
    expect(localStorage.getItem("stash_sidebar_open_sections")).toBeNull();
  });
});
