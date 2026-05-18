import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import type { MouseEvent, ReactNode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import AppSidebar from "./AppSidebar";
import { resetStashNavigationCache } from "../lib/stashNavigationCache";
import { ShareModalProvider } from "../lib/shareModalContext";
import {
  createPage,
  getFolderContents,
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
  createPage: vi.fn(),
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

const sidebarWithStash = {
  sessions: [
    {
      id: "session-row-1",
      session_id: "session-1",
      title: "Planning session",
      agent_name: "Codex",
      size_bytes: 256,
      last_at: "2026-05-11T00:00:00Z",
      updated_at: "2026-05-11T00:00:00Z",
    },
  ],
  files: {
    folders: [],
    pages: [],
    files: [],
  },
  stashes: [
    {
      id: "stash-1",
      workspace_id: "ws-1",
      slug: "project-alpha",
      title: "Project Alpha",
      description: "",
      access: "workspace" as const,
      discoverable: false,
      is_external: false,
      forked_from_stash_id: null,
      item_count: 1,
      items: [
        {
          object_type: "session" as const,
          object_id: "session-row-1",
          label_override: "Launch session",
          position: 0,
        },
      ],
      updated_at: "2026-05-11T00:00:00Z",
    },
  ],
};

const sidebarWithTree = {
  sessions: [
    {
      id: "session-row-1",
      session_id: "session-1",
      title: "Planning session",
      agent_name: "Codex",
      size_bytes: 256,
      last_at: "2026-05-11T00:00:00Z",
      updated_at: "2026-05-11T00:00:00Z",
    },
  ],
  files: {
    folders: [
      {
        id: "folder-1",
        name: "Product",
        parent_folder_id: null,
        page_count: 1,
        file_count: 0,
        has_skill: false,
      },
    ],
    pages: [
      {
        id: "page-root",
        name: "Overview",
        folder_id: null,
      },
    ],
    files: [],
  },
  stashes: [],
};

function detailsFor(label: string): HTMLDetailsElement {
  const details = screen.getByText(label).closest("details");
  if (!details) throw new Error(`No details element for ${label}`);
  return details as HTMLDetailsElement;
}

function openSectionState(): Record<string, boolean> {
  return JSON.parse(localStorage.getItem("stash_sidebar_open_sections") ?? "{}");
}

function renderSidebar() {
  return render(
    <ShareModalProvider>
      <AppSidebar user={user} onCmdkOpen={vi.fn()} />
    </ShareModalProvider>
  );
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
    vi.mocked(getFolderContents).mockResolvedValue({
      folder: { id: "folder-1", name: "Product", parent_folder_id: null },
      breadcrumbs: [],
      subfolders: [],
      pages: [{ id: "page-child", name: "Roadmap" }],
      files: [],
    });
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
    vi.mocked(createPage).mockResolvedValue({
      id: "page-new",
      workspace_id: "ws-1",
      folder_id: null,
      name: "New page",
      content_type: "markdown",
      content_markdown: "",
      content_html: "",
      html_layout: "responsive",
      created_by: "user-1",
      updated_by: null,
      created_at: "2026-05-11T00:00:00Z",
      updated_at: "2026-05-11T00:00:00Z",
    });
  });

  afterEach(() => {
    cleanup();
  });

  it("starts top-level sections expanded", async () => {
    renderSidebar();

    await screen.findByText("Sessions");

    await waitFor(() => expect(getWorkspaceSidebar).toHaveBeenCalledWith("ws-1"));
    expect(detailsFor("Sessions")).toHaveAttribute("open");
    expect(detailsFor("Files")).toHaveAttribute("open");
    expect(detailsFor("Stashes")).toHaveAttribute("open");
  });

  it("renders shared memberships in their own group", async () => {
    vi.mocked(listMyWorkspaces).mockResolvedValue({
      workspaces: [workspace, sharedWorkspace],
    });

    renderSidebar();

    await screen.findByText("Shared Stash");

    const sidebarText = document.body.textContent ?? "";
    expect(sidebarText.indexOf("SHARED WORKSPACES")).toBeLessThan(
      sidebarText.indexOf("Shared Stash")
    );
    expect(screen.getAllByText("Shared Stash")).toHaveLength(1);
  });

  it("restores explicit section state from localStorage", async () => {
    localStorage.setItem(
      "stash_sidebar_open_sections",
      JSON.stringify({ "ws-1:files": false })
    );

    renderSidebar();

    await screen.findByText("Sessions");

    expect(detailsFor("Sessions")).toHaveAttribute("open");
    expect(detailsFor("Files")).not.toHaveAttribute("open");
    expect(detailsFor("Stashes")).toHaveAttribute("open");
    expect(getWorkspaceSidebar).toHaveBeenCalledWith("ws-1");
  });

  it("opens the Sessions section when its header is clicked", async () => {
    localStorage.setItem(
      "stash_sidebar_open_sections",
      JSON.stringify({ "ws-1:sessions": false })
    );

    renderSidebar();

    await screen.findByText("Sessions");
    expect(detailsFor("Sessions")).not.toHaveAttribute("open");

    fireEvent.click(screen.getByRole("link", { name: "Sessions" }));

    expect(detailsFor("Sessions")).toHaveAttribute("open");
    expect(openSectionState()["ws-1:sessions"]).toBe(true);
  });

  it("opens the Files section when its header is clicked", async () => {
    localStorage.setItem(
      "stash_sidebar_open_sections",
      JSON.stringify({ "ws-1:files": false })
    );

    renderSidebar();

    await screen.findByText("Files");
    expect(detailsFor("Files")).not.toHaveAttribute("open");

    fireEvent.click(screen.getByText("Files"));

    expect(detailsFor("Files")).toHaveAttribute("open");
    expect(openSectionState()["ws-1:files"]).toBe(true);
  });

  it("opens session day folders from the day row without closing on repeat clicks", async () => {
    vi.mocked(getWorkspaceSidebar).mockResolvedValue(sidebarWithTree);

    renderSidebar();

    const day = await screen.findByText(/May 11/);
    expect(detailsFor(day.textContent ?? "")).not.toHaveAttribute("open");

    fireEvent.click(day);
    expect(detailsFor(day.textContent ?? "")).toHaveAttribute("open");
    expect(screen.getByText("Planning session")).toBeTruthy();

    fireEvent.click(day);
    expect(detailsFor(day.textContent ?? "")).toHaveAttribute("open");
  });

  it("creates pages from the native sidebar modal", async () => {
    const promptSpy = vi.spyOn(window, "prompt");
    vi.mocked(getWorkspaceSidebar).mockResolvedValue(sidebarWithTree);

    renderSidebar();

    fireEvent.click(await screen.findByLabelText("Add page"));

    expect(promptSpy).not.toHaveBeenCalled();
    expect(screen.getByRole("heading", { name: "New page" })).toBeTruthy();

    fireEvent.change(screen.getByPlaceholderText("Untitled"), {
      target: { value: "Launch notes" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Create" }));

    await waitFor(() => expect(createPage).toHaveBeenCalledWith("ws-1", "Launch notes"));
    await waitFor(() => expect(nav.push).toHaveBeenCalledWith("/workspaces/ws-1/p/page-new"));

    promptSpy.mockRestore();
  });

  it("closes the native sidebar modal with Escape", async () => {
    vi.mocked(getWorkspaceSidebar).mockResolvedValue(sidebarWithTree);

    renderSidebar();

    fireEvent.click(await screen.findByLabelText("Add page"));
    expect(screen.getByRole("heading", { name: "New page" })).toBeTruthy();

    fireEvent.keyDown(document, { key: "Escape" });

    expect(screen.queryByRole("heading", { name: "New page" })).not.toBeInTheDocument();
  });

  it("opens the Files section when a top-level page is clicked", async () => {
    localStorage.setItem(
      "stash_sidebar_open_sections",
      JSON.stringify({ "ws-1:files": false })
    );
    vi.mocked(getWorkspaceSidebar).mockResolvedValue(sidebarWithTree);

    renderSidebar();

    await screen.findByText("Overview");
    expect(openSectionState()["ws-1:files"]).toBe(false);

    fireEvent.click(screen.getByText("Overview"));

    expect(openSectionState()["ws-1:files"]).toBe(true);
  });

  it("opens folder rows when their label is clicked", async () => {
    vi.mocked(getWorkspaceSidebar).mockResolvedValue(sidebarWithTree);

    renderSidebar();

    await screen.findByText("Product");
    expect(detailsFor("Product")).not.toHaveAttribute("open");

    fireEvent.click(screen.getByText("Product"));

    expect(detailsFor("Product")).toHaveAttribute("open");
    await waitFor(() => expect(getFolderContents).toHaveBeenCalledWith("ws-1", "folder-1"));
    expect(await screen.findByText("Roadmap")).toBeTruthy();
  });

  it("keeps the workspace landing route open by default", async () => {
    nav.pathname = "/workspaces/ws-1";

    renderSidebar();

    await screen.findByText("Sessions");

    expect(detailsFor("Sessions")).toHaveAttribute("open");
    expect(detailsFor("Files")).toHaveAttribute("open");
    expect(detailsFor("Stashes")).toHaveAttribute("open");
  });

  it("links sidebar settings to the active workspace settings page", async () => {
    nav.pathname = "/workspaces/ws-1/sessions";

    renderSidebar();

    await screen.findByText("Sessions");

    expect(screen.getByRole("link", { name: "Settings" })).toHaveAttribute(
      "href",
      "/workspaces/ws-1/settings"
    );
  });

  it("keeps deep-linked tree sections open by default", async () => {
    nav.pathname = "/workspaces/ws-1/p/page-1";

    renderSidebar();

    await screen.findByText("Sessions");

    expect(detailsFor("Sessions")).toHaveAttribute("open");
    expect(detailsFor("Files")).toHaveAttribute("open");
    expect(detailsFor("Stashes")).toHaveAttribute("open");
    expect(localStorage.getItem("stash_sidebar_open_workspaces")).toBeNull();
  });

  it("reuses loaded workspace and spine data after a remount", async () => {
    nav.pathname = "/workspaces/ws-1/p/page-1";

    const first = renderSidebar();
    await screen.findByText("Sessions");
    await waitFor(() => expect(getWorkspaceSidebar).toHaveBeenCalledWith("ws-1"));
    expect(listMyWorkspaces).toHaveBeenCalledTimes(1);
    expect(getWorkspaceSidebar).toHaveBeenCalledTimes(1);

    first.unmount();
    vi.clearAllMocks();

    renderSidebar();

    await screen.findByText("Sessions");
    expect(listMyWorkspaces).not.toHaveBeenCalled();
    expect(getWorkspaceSidebar).not.toHaveBeenCalled();
    expect(detailsFor("Sessions")).toHaveAttribute("open");
  });

  it("collapses individual stashes and restores that browser state", async () => {
    vi.mocked(getWorkspaceSidebar).mockResolvedValue(sidebarWithStash);

    const first = renderSidebar();

    await screen.findByText("Project Alpha");
    expect(screen.getByText("Launch session")).toBeTruthy();

    fireEvent.click(screen.getByLabelText("Collapse Project Alpha"));

    expect(screen.queryByText("Launch session")).toBeNull();
    expect(localStorage.getItem("stash_sidebar_collapsed_stashes")).toBe(
      JSON.stringify({ "ws-1:stash-1": true })
    );

    first.unmount();

    renderSidebar();

    await screen.findByText("Project Alpha");
    expect(screen.queryByText("Launch session")).toBeNull();

    fireEvent.click(screen.getByLabelText("Expand Project Alpha"));

    expect(await screen.findByText("Launch session")).toBeTruthy();
    expect(localStorage.getItem("stash_sidebar_collapsed_stashes")).toBe("{}");
  });

  it("rejects non-jsonl files dropped on the Sessions section", async () => {
    localStorage.setItem("stash_sidebar_open_workspaces", JSON.stringify({ "ws-1": true }));
    localStorage.setItem(
      "stash_sidebar_open_sections",
      JSON.stringify({ "ws-1:sessions": true })
    );

    renderSidebar();

    await screen.findByText("Sessions");

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

    renderSidebar();

    await screen.findByText("Files");

    const file = new File(["hello"], "brief.md", { type: "text/markdown" });
    fireEvent.drop(detailsFor("Files"), {
      dataTransfer: { types: ["Files"], files: [file] },
    });

    await waitFor(() => expect(uploadFile).toHaveBeenCalledWith("ws-1", file));
    expect(await screen.findByText("1 file added.")).toBeTruthy();
  });
});
