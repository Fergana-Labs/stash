import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import AppSidebar from "./AppSidebar";
import { resetStashNavigationCache } from "../lib/stashNavigationCache";
import {
  getWorkspaceSidebar,
  listMyWorkspaces,
  uploadFile,
  uploadTranscript,
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
  getWorkspaceSidebar: vi.fn(),
  listMyWorkspaces: vi.fn(),
  uploadFile: vi.fn(),
  uploadTranscript: vi.fn(),
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

const sharedWorkspace = {
  ...workspace,
  id: "ws-2",
  name: "Shared Stash",
  creator_id: "user-2",
  invite_code: "shared",
};

const emptySidebar = {
  sessions: [],
  files: {
    folders: [],
    pages: [],
    files: [],
  },
  stashes: [],
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
    vi.mocked(getWorkspaceSidebar).mockResolvedValue(emptySidebar);
    vi.mocked(uploadFile).mockResolvedValue({
      id: "file-1",
      workspace_id: "ws-1",
      folder_id: null,
      name: "brief.md",
      content_type: "text/markdown",
      size_bytes: 5,
      url: "/files/file-1",
      uploaded_by: "user-1",
      created_at: "2026-05-11T00:00:00Z",
      linked_table_id: null,
    });
    vi.mocked(uploadTranscript).mockResolvedValue({
      session_id: "session-1",
      imported: 1,
      skipped: false,
    });
  });

  afterEach(() => {
    cleanup();
  });

  it("starts workspaces and their top-level sections collapsed", async () => {
    render(<AppSidebar user={user} onCmdkOpen={vi.fn()} />);

    await screen.findByText("Demo Stash");

    const activityLinks = screen.getAllByText("Activity").map((node) => node.closest("a"));
    expect(activityLinks.some((link) => link?.getAttribute("href") === "/activity")).toBe(true);
    expect(activityLinks.some((link) => link?.getAttribute("href") === "/activity?workspace=ws-1")).toBe(true);
    expect(detailsFor("Demo Stash")).not.toHaveAttribute("open");
    expect(detailsFor("Sessions")).not.toHaveAttribute("open");
    expect(detailsFor("Files")).not.toHaveAttribute("open");
    expect(detailsFor("Stashes")).not.toHaveAttribute("open");
    expect(getWorkspaceSidebar).not.toHaveBeenCalled();
  });

  it("splits owned and shared memberships", async () => {
    vi.mocked(listMyWorkspaces).mockResolvedValue({
      workspaces: [workspace, sharedWorkspace],
    });

    render(<AppSidebar user={user} onCmdkOpen={vi.fn()} />);

    await screen.findByText("Shared Stash");
    await screen.findByText("Demo Stash");

    const sidebarText = document.body.textContent ?? "";
    expect(sidebarText.indexOf("SHARED WORKSPACES")).toBeLessThan(
      sidebarText.indexOf("Shared Stash")
    );
    expect(sidebarText.indexOf("Shared Stash")).toBeLessThan(
      sidebarText.indexOf("MY WORKSPACES")
    );
    expect(sidebarText.indexOf("MY WORKSPACES")).toBeLessThan(
      sidebarText.indexOf("Demo Stash")
    );
    expect(screen.getAllByText("Shared Stash")).toHaveLength(1);
  });

  it("restores explicit expanded state from localStorage", async () => {
    localStorage.setItem("stash_sidebar_open_workspaces", JSON.stringify({ "ws-1": true }));
    localStorage.setItem(
      "stash_sidebar_open_sections",
      JSON.stringify({ "ws-1:sessions": true })
    );

    render(<AppSidebar user={user} onCmdkOpen={vi.fn()} />);

    await screen.findByText("Demo Stash");

    await waitFor(() => expect(detailsFor("Demo Stash")).toHaveAttribute("open"));
    expect(detailsFor("Sessions")).toHaveAttribute("open");
    expect(detailsFor("Files")).not.toHaveAttribute("open");
    expect(detailsFor("Stashes")).not.toHaveAttribute("open");
    expect(getWorkspaceSidebar).toHaveBeenCalledWith("ws-1");
  });

  it("keeps the workspace landing route collapsed without saved state", async () => {
    nav.pathname = "/workspaces/ws-1";

    render(<AppSidebar user={user} onCmdkOpen={vi.fn()} />);

    await screen.findByText("Demo Stash");

    expect(detailsFor("Demo Stash")).not.toHaveAttribute("open");
    expect(detailsFor("Sessions")).not.toHaveAttribute("open");
    expect(detailsFor("Files")).not.toHaveAttribute("open");
    expect(detailsFor("Stashes")).not.toHaveAttribute("open");
    expect(getWorkspaceSidebar).not.toHaveBeenCalled();
  });

  it("opens the relevant tree branch for deep links only", async () => {
    nav.pathname = "/workspaces/ws-1/p/page-1";

    render(<AppSidebar user={user} onCmdkOpen={vi.fn()} />);

    await screen.findByText("Demo Stash");

    await waitFor(() => expect(detailsFor("Demo Stash")).toHaveAttribute("open"));
    expect(detailsFor("Sessions")).not.toHaveAttribute("open");
    expect(detailsFor("Files")).toHaveAttribute("open");
    expect(localStorage.getItem("stash_sidebar_open_workspaces")).toBeNull();
    expect(localStorage.getItem("stash_sidebar_open_sections")).toBeNull();
  });

  it("reuses loaded workspace and spine data after a remount", async () => {
    nav.pathname = "/workspaces/ws-1/p/page-1";

    const first = render(<AppSidebar user={user} onCmdkOpen={vi.fn()} />);
    await screen.findByText("Demo Stash");
    await waitFor(() => expect(getWorkspaceSidebar).toHaveBeenCalledWith("ws-1"));
    expect(listMyWorkspaces).toHaveBeenCalledTimes(1);
    expect(getWorkspaceSidebar).toHaveBeenCalledTimes(1);

    first.unmount();
    vi.clearAllMocks();

    render(<AppSidebar user={user} onCmdkOpen={vi.fn()} />);

    await screen.findByText("Demo Stash");
    expect(listMyWorkspaces).not.toHaveBeenCalled();
    expect(getWorkspaceSidebar).not.toHaveBeenCalled();
    expect(detailsFor("Demo Stash")).toHaveAttribute("open");
  });

  it("rejects non-jsonl files dropped on the Sessions section", async () => {
    localStorage.setItem("stash_sidebar_open_workspaces", JSON.stringify({ "ws-1": true }));
    localStorage.setItem(
      "stash_sidebar_open_sections",
      JSON.stringify({ "ws-1:sessions": true })
    );

    render(<AppSidebar user={user} onCmdkOpen={vi.fn()} />);

    await screen.findByText("Demo Stash");

    const file = new File(["deck"], "launch-plan.pptx", {
      type: "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    });
    fireEvent.drop(detailsFor("Sessions"), {
      dataTransfer: { types: ["Files"], files: [file] },
    });

    expect(await screen.findByText("Sessions only accept .jsonl transcripts.")).toBeTruthy();
    expect(uploadTranscript).not.toHaveBeenCalled();
  });

  it("uploads files dropped on the Files section", async () => {
    localStorage.setItem("stash_sidebar_open_workspaces", JSON.stringify({ "ws-1": true }));
    localStorage.setItem(
      "stash_sidebar_open_sections",
      JSON.stringify({ "ws-1:files": true })
    );

    render(<AppSidebar user={user} onCmdkOpen={vi.fn()} />);

    await screen.findByText("Demo Stash");

    const file = new File(["hello"], "brief.md", { type: "text/markdown" });
    fireEvent.drop(detailsFor("Files"), {
      dataTransfer: { types: ["Files"], files: [file] },
    });

    await waitFor(() => expect(uploadFile).toHaveBeenCalledWith("ws-1", file));
    expect(await screen.findByText("1 file added.")).toBeTruthy();
  });
});
