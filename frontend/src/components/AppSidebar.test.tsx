import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
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
  uploadFileOrPage,
  uploadTranscript,
  type WorkspaceSidebarSession,
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
  uploadFileOrPage: vi.fn(),
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
      linear_tickets: [],
      user_name: "Henry",
      agent_name: "Claude",
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
      workspace_permission: "read" as const,
      public_permission: "none" as const,
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

const sidebarWithStashFiles = {
  sessions: [],
  files: {
    folders: [],
    pages: [
      {
        id: "page-root",
        name: "Overview",
        content_type: "markdown" as const,
        folder_id: null,
      },
    ],
    files: [
      {
        id: "file-1",
        workspace_id: "ws-1",
        folder_id: null,
        name: "Launch brief.md",
        size_bytes: 12,
        content_type: "text/markdown",
        url: null,
        created_at: "2026-05-11T00:00:00Z",
        linked_table_id: null,
      },
      {
        id: "file-csv",
        workspace_id: "ws-1",
        folder_id: null,
        name: "Launch data.csv",
        size_bytes: 12,
        content_type: "text/csv",
        url: null,
        created_at: "2026-05-11T00:00:00Z",
        linked_table_id: "table-1",
      },
    ],
  },
  stashes: [
    {
      id: "stash-1",
      workspace_id: "ws-1",
      slug: "project-alpha",
      title: "Project Alpha",
      description: "",
      access: "workspace" as const,
      workspace_permission: "read" as const,
      public_permission: "none" as const,
      discoverable: false,
      is_external: false,
      forked_from_stash_id: null,
      item_count: 3,
      items: [
        {
          object_type: "page" as const,
          object_id: "page-root",
          label_override: "Launch page",
          position: 0,
        },
        {
          object_type: "file" as const,
          object_id: "file-1",
          label_override: "Launch file",
          position: 1,
        },
        {
          object_type: "file" as const,
          object_id: "file-csv",
          label_override: "Launch table file",
          position: 2,
        },
      ],
      updated_at: "2026-05-11T00:00:00Z",
    },
  ],
};

const sidebarWithNestedStashItems = {
  sessions: [],
  files: {
    folders: [
      {
        id: "folder-product",
        name: "Product",
        parent_folder_id: null,
        page_count: 1,
        file_count: 0,
        has_skill: false,
      },
    ],
    pages: [
      {
        id: "page-polish",
        name: "Sidebar polish notes",
        content_type: "markdown" as const,
        folder_id: "folder-product",
      },
      {
        id: "page-hover",
        name: "Hover QA notes",
        content_type: "markdown" as const,
        folder_id: null,
      },
    ],
    files: [
      {
        id: "file-table",
        workspace_id: "ws-1",
        folder_id: "folder-product",
        name: "service-matrix.csv",
        size_bytes: 12,
        content_type: "text/csv",
        url: null,
        created_at: "2026-05-11T00:00:00Z",
        linked_table_id: "table-1",
      },
    ],
  },
  stashes: [
    {
      id: "stash-1",
      workspace_id: "ws-1",
      slug: "sidebar-review-kit",
      title: "Sidebar Review Kit",
      description: "",
      access: "workspace" as const,
      workspace_permission: "read" as const,
      public_permission: "none" as const,
      discoverable: false,
      is_external: false,
      forked_from_stash_id: null,
      item_count: 5,
      items: [
        {
          object_type: "page" as const,
          object_id: "page-polish",
          label_override: "Product/Sidebar polish notes",
          position: 0,
        },
        {
          object_type: "folder" as const,
          object_id: "folder-product",
          label_override: "Custom product folder",
          position: 1,
        },
        {
          object_type: "page" as const,
          object_id: "page-hover",
          label_override: "Hover QA notes",
          position: 2,
        },
        {
          object_type: "file" as const,
          object_id: "file-table",
          label_override: "CSV-backed service matrix",
          position: 3,
        },
        {
          object_type: "table" as const,
          object_id: "table-1",
          label_override: "Feature readiness table",
          position: 4,
        },
      ],
      updated_at: "2026-05-11T00:00:00Z",
    },
  ],
};

const sidebarWithTwoStashes = {
  ...sidebarWithStash,
  stashes: [
    ...sidebarWithStash.stashes,
    {
      ...sidebarWithStash.stashes[0],
      id: "stash-2",
      slug: "agent-notes",
      title: "Agent Notes",
      items: [
        {
          object_type: "session" as const,
          object_id: "session-row-1",
          label_override: "Shared session",
          position: 0,
        },
      ],
    },
  ],
};

const sidebarWithTree = {
  sessions: [
    {
      id: "session-row-1",
      session_id: "session-1",
      title: "Planning session",
      linear_tickets: [],
      user_name: "Henry",
      agent_name: "Claude",
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
        content_type: "markdown" as const,
        folder_id: null,
      },
    ],
    files: [],
  },
  stashes: [],
};

function sidebarSession(
  sessionId: string,
  title: string,
  userName: string,
  lastAt: string,
  linearTickets: WorkspaceSidebarSession["linear_tickets"] = []
) {
  return {
    id: `row-${sessionId}`,
    session_id: sessionId,
    title,
    linear_tickets: linearTickets,
    user_name: userName,
    agent_name: "Claude",
    size_bytes: 256,
    last_at: lastAt,
    updated_at: lastAt,
  };
}

function linearTicket(
  identifier: string,
  title: string | null = null
): WorkspaceSidebarSession["linear_tickets"][number] {
  return {
    ticket_identifier: identifier,
    ticket_title: title,
    ticket_url: null,
    source: "github_pr_title",
    confidence: 0.9,
    linear_issue_id: null,
    ticket_status: null,
    ticket_assignee_name: null,
    ticket_team_key: null,
    ticket_team_name: null,
    ticket_project_name: null,
    linear_updated_at: null,
    enriched_at: null,
  };
}

function sidebarWithSessions(sessions: ReturnType<typeof sidebarSession>[]) {
  return {
    sessions,
    files: {
      folders: [],
      pages: [],
      files: [],
    },
    stashes: [],
  };
}

function expectedSidebarTimestamp(iso: string, includeDate = true): string {
  const date = new Date(iso);
  const hour24 = date.getHours();
  const hour = hour24 % 12 || 12;
  const minutes = String(date.getMinutes()).padStart(2, "0");
  const suffix = hour24 >= 12 ? "p" : "a";
  const time = `${hour}:${minutes}${suffix}`;

  if (!includeDate) return time;
  return `${date.getMonth() + 1}/${date.getDate()} ${time}`;
}

function sidebarWithFiles({
  folderCount,
  pages = [],
  files = [],
}: {
  folderCount: number;
  pages?: Array<{ id: string; name: string; folder_id: string | null }>;
  files?: Array<{ id: string; name: string; folder_id: string | null }>;
}) {
  return {
    sessions: [],
    files: {
      folders: Array.from({ length: folderCount }, (_, index) => ({
        id: `folder-${index + 1}`,
        name: `${String(index + 1).padStart(2, "0")} Root Folder`,
        parent_folder_id: null,
        page_count: 0,
        file_count: 0,
        has_skill: false,
      })),
      pages: pages.map((page) => ({
        ...page,
        content_type: "markdown" as const,
      })),
      files: files.map((file) => ({
        ...file,
        workspace_id: "ws-1",
        size_bytes: 12,
        content_type: "text/markdown",
        url: null,
        created_at: "2026-05-11T00:00:00Z",
        linked_table_id: null,
      })),
    },
    stashes: [],
  };
}

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
      pages: [{ id: "page-child", name: "Roadmap", content_type: "markdown" }],
      files: [],
    });
    vi.mocked(uploadFileOrPage).mockResolvedValue({
      kind: "file",
      file: {
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
      },
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

  it("lists shared memberships in the workspace switcher dropdown", async () => {
    vi.mocked(listMyWorkspaces).mockResolvedValue({
      workspaces: [workspace, sharedWorkspace],
    });

    renderSidebar();

    // The switcher button shows the active workspace label and a chevron;
    // opening it surfaces shared memberships under their own group label.
    const switcher = await screen.findByRole("button", { expanded: false });
    switcher.click();

    await screen.findByText(/Shared with you/i);
    await screen.findByText("Shared Stash");
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

  it("keeps the first session bucket open and refuses to close on repeat row clicks", async () => {
    vi.mocked(getWorkspaceSidebar).mockResolvedValue(sidebarWithTree);

    renderSidebar();

    // The first (most recent) bucket renders open by default so the user sees
    // recent sessions without having to drill in. Clicking the row should
    // never collapse it — only the chevron can collapse.
    const day = await screen.findByText(/May 11/);
    expect(detailsFor(day.textContent ?? "")).toHaveAttribute("open");
    expect(screen.getByText("Henry")).toBeTruthy();
    expect(screen.queryByText("Claude")).toBeNull();
    expect(screen.getByText("Planning session")).toBeTruthy();

    fireEvent.click(day);
    expect(detailsFor(day.textContent ?? "")).toHaveAttribute("open");
  });

  it("shows compact timestamps on session rows", async () => {
    const lastAt = "2026-05-20T12:59:00";
    vi.mocked(getWorkspaceSidebar).mockResolvedValue(
      sidebarWithSessions([
        sidebarSession("timestamped", "Timestamped session", "Henry", lastAt),
      ])
    );

    renderSidebar();

    expect(await screen.findByText("Timestamped session")).toBeTruthy();
    const timestamp = screen.getByText(expectedSidebarTimestamp(lastAt, false));
    expect(timestamp.tagName).toBe("TIME");
    expect(timestamp).toHaveAttribute("dateTime", lastAt);

    fireEvent.change(screen.getByLabelText("Filter sessions"), {
      target: { value: "timestamped" },
    });
    expect(screen.getByText(expectedSidebarTimestamp(lastAt))).toBeTruthy();
  });

  it("limits visible session periods and reveals more on demand", async () => {
    vi.mocked(getWorkspaceSidebar).mockResolvedValue(
      sidebarWithSessions(
        Array.from({ length: 11 }, (_, index) =>
          sidebarSession(
            `period-${index}`,
            `Period ${index}`,
            "Henry",
            `2026-05-${String(20 - index).padStart(2, "0")}T12:00:00Z`
          )
        )
      )
    );

    renderSidebar();

    expect(await screen.findByText("Period 0")).toBeTruthy();
    expect(screen.queryByText("Period 10")).toBeNull();

    fireEvent.click(screen.getByRole("button", { name: "Show 1 more periods" }));

    expect(screen.getByText("Period 10")).toBeTruthy();
  });

  it("limits visible users within a session period", async () => {
    vi.mocked(getWorkspaceSidebar).mockResolvedValue(
      sidebarWithSessions(
        Array.from({ length: 11 }, (_, index) =>
          sidebarSession(
            `user-${index}`,
            `User ${index} session`,
            `User ${index}`,
            `2026-05-20T${String(23 - index).padStart(2, "0")}:00:00Z`
          )
        )
      )
    );

    renderSidebar();

    expect(await screen.findByText("User 0")).toBeTruthy();
    expect(screen.queryByText("User 10")).toBeNull();

    fireEvent.click(screen.getByRole("button", { name: "Show 1 more users" }));

    expect(screen.getByText("User 10")).toBeTruthy();
  });

  it("limits visible sessions within a user bucket", async () => {
    vi.mocked(getWorkspaceSidebar).mockResolvedValue(
      sidebarWithSessions(
        Array.from({ length: 11 }, (_, index) =>
          sidebarSession(
            `session-${index}`,
            `Bucket session ${index}`,
            "Henry",
            `2026-05-20T12:${String(59 - index).padStart(2, "0")}:00Z`
          )
        )
      )
    );

    renderSidebar();

    expect(await screen.findByText("Bucket session 0")).toBeTruthy();
    expect(screen.queryByText("Bucket session 10")).toBeNull();

    fireEvent.click(screen.getByText("Henry"));
    fireEvent.click(screen.getByRole("button", { name: "Show 1 more sessions" }));

    expect(screen.getByText("Bucket session 10")).toBeTruthy();
  });

  it("renders Linear ticket pills for session rows", async () => {
    vi.mocked(getWorkspaceSidebar).mockResolvedValue(
      sidebarWithSessions([
        sidebarSession(
          "ticket-session",
          "Ticketed sidebar work",
          "Henry",
          "2026-05-20T12:00:00Z",
          [linearTicket("FER-19", "Label sessions from PRs")]
        ),
      ])
    );

    renderSidebar();

    const pill = await screen.findByText("FER-19");
    expect(pill).toHaveAttribute("title", "FER-19: Label sessions from PRs");
    expect(pill).toHaveClass("opacity-0");
    expect(pill).toHaveClass("group-hover/nav:opacity-100");
  });

  it("filters hidden sidebar sessions", async () => {
    vi.mocked(getWorkspaceSidebar).mockResolvedValue(
      sidebarWithSessions(
        Array.from({ length: 11 }, (_, index) =>
          sidebarSession(
            `search-${index}`,
            index === 10 ? "Unique hidden decision" : `Search session ${index}`,
            "Henry",
            `2026-05-20T12:${String(59 - index).padStart(2, "0")}:00Z`
          )
        )
      )
    );

    renderSidebar();

    await screen.findByText("Search session 0");
    expect(screen.queryByText("Unique hidden decision")).toBeNull();

    fireEvent.change(screen.getByLabelText("Filter sessions"), {
      target: { value: "unique hidden" },
    });

    expect(screen.getByText("Unique hidden decision")).toBeTruthy();
  });

  it("pins sessions from the sidebar context menu", async () => {
    vi.mocked(getWorkspaceSidebar).mockResolvedValue(sidebarWithTree);

    renderSidebar();

    fireEvent.click(await screen.findByText("Henry"));
    const sessionLink = await screen.findByRole("link", { name: /Planning session/ });
    fireEvent.contextMenu(sessionLink);
    fireEvent.click(screen.getByRole("menuitem", { name: "Pin Planning session" }));

    expect(screen.getByText("Pinned (1)")).toBeTruthy();
    expect(JSON.parse(localStorage.getItem("stash_sidebar_pinned_items") ?? "{}")).toEqual({
      "ws-1": {
        sessions: ["session-1"],
        folders: [],
        files: [],
      },
    });
  });

  it("uses one combined show-more row for files", async () => {
    vi.mocked(getWorkspaceSidebar).mockResolvedValue(
      sidebarWithFiles({
        folderCount: 11,
        pages: [{ id: "root-page", name: "Root Page", folder_id: null }],
        files: [{ id: "root-file", name: "Root File.md", folder_id: null }],
      })
    );

    renderSidebar();

    expect(await screen.findByText("01 Root Folder")).toBeTruthy();
    expect(screen.queryByText("11 Root Folder")).toBeNull();
    expect(screen.queryByText("Root Page")).toBeNull();
    expect(screen.queryByRole("button", { name: /more folders/i })).toBeNull();
    expect(screen.queryByRole("button", { name: /more pages/i })).toBeNull();
    expect(screen.queryByRole("button", { name: /more files/i })).toBeNull();

    fireEvent.click(screen.getByRole("button", { name: "Show 3 more items" }));

    expect(screen.getByText("11 Root Folder")).toBeTruthy();
    expect(screen.getByText("Root Page")).toBeTruthy();
    expect(screen.getByText("Root File.md")).toBeTruthy();
  });

  it("keeps pinned folders expandable", async () => {
    localStorage.setItem(
      "stash_sidebar_pinned_items",
      JSON.stringify({
        "ws-1": { sessions: [], folders: ["folder-1"], files: [] },
      })
    );
    localStorage.setItem(
      "stash_sidebar_pinned_item_labels",
      JSON.stringify({
        "ws-1": { sessions: {}, folders: { "folder-1": "Product" }, files: {} },
      })
    );
    vi.mocked(getWorkspaceSidebar).mockResolvedValue(sidebarWithTree);

    renderSidebar();

    await screen.findByText("Pinned (1)");
    expect(detailsFor("Product")).not.toHaveAttribute("open");

    fireEvent.click(screen.getByText("Product"));

    expect(detailsFor("Product")).toHaveAttribute("open");
    await waitFor(() =>
      expect(getFolderContents).toHaveBeenCalledWith("ws-1", "folder-1")
    );
    expect(await screen.findByText("Roadmap")).toBeTruthy();
  });

  it("filters hidden sidebar files", async () => {
    vi.mocked(getWorkspaceSidebar).mockResolvedValue({
      sessions: [],
      files: {
        folders: [
          {
            id: "folder-parent",
            name: "00 Huge Folder",
            parent_folder_id: null,
            page_count: 1,
            file_count: 1,
            has_skill: false,
          },
          ...Array.from({ length: 10 }, (_, index) => ({
            id: `folder-${index + 1}`,
            name: `${String(index + 1).padStart(2, "0")} Root Folder`,
            parent_folder_id: null,
            page_count: 0,
            file_count: 0,
            has_skill: false,
          })),
        ],
        pages: [
          {
            id: "deep-page",
            name: "Deep Search Page",
            content_type: "markdown" as const,
            folder_id: "folder-parent",
          },
        ],
        files: [
          {
            id: "deep-file",
            name: "Deep Search File.md",
            folder_id: "folder-parent",
            size_bytes: 12,
            content_type: "text/markdown",
            url: null,
            created_at: "2026-05-11T00:00:00Z",
            linked_table_id: null,
          },
        ],
      },
      stashes: [],
    });

    renderSidebar();

    await screen.findByText("00 Huge Folder");
    expect(screen.queryByText("00 Huge Folder/Deep Search File.md")).toBeNull();

    fireEvent.change(screen.getByLabelText("Filter files"), {
      target: { value: "deep search" },
    });

    expect(screen.getByText("00 Huge Folder/Deep Search Page")).toBeTruthy();
    expect(screen.getByText("00 Huge Folder/Deep Search File.md")).toBeTruthy();
  });

  it("creates pages from the native sidebar modal", async () => {
    const promptSpy = vi.spyOn(window, "prompt");
    vi.mocked(getWorkspaceSidebar).mockResolvedValue(sidebarWithTree);

    renderSidebar();

    const addRow = await screen.findByRole("button", { name: /\+\s*New page/ });
    fireEvent.click(addRow);

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

    // "+ New page" is the row button at the bottom of the Files section.
    fireEvent.click(await screen.findByRole("button", { name: /\+\s*New page/ }));
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

  it("links sidebar members to the active workspace members page", async () => {
    nav.pathname = "/workspaces/ws-1/sessions";

    renderSidebar();

    await screen.findByText("Sessions");

    expect(screen.getByRole("link", { name: "Members" })).toHaveAttribute(
      "href",
      "/workspaces/ws-1/members"
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

  it("persists each stash open state across remounts", async () => {
    vi.mocked(getWorkspaceSidebar).mockResolvedValue(sidebarWithStash);

    const first = renderSidebar();

    await screen.findByText("Project Alpha");
    // Stashes default to closed — opening the Stashes section shouldn't
    // explode every stash's items at once.
    expect(screen.queryByText("Launch session")).toBeNull();

    fireEvent.click(screen.getByLabelText("Expand Project Alpha"));
    expect(await screen.findByText("Launch session")).toBeTruthy();

    expect(localStorage.getItem("stash_sidebar_open_stashes")).toBe(
      JSON.stringify({ "ws-1:stash-1": true })
    );

    first.unmount();

    renderSidebar();
    await screen.findByText("Project Alpha");
    expect(await screen.findByText("Launch session")).toBeTruthy();
  });

  it("nests stash items under included parent folders", async () => {
    vi.mocked(getWorkspaceSidebar).mockResolvedValue(sidebarWithNestedStashItems);

    renderSidebar();

    await screen.findByText("Sidebar Review Kit");
    fireEvent.click(screen.getByLabelText("Expand Sidebar Review Kit"));

    const stashes = detailsFor("Stashes");
    const productDetails = within(stashes).getByText("Product").closest("details");
    if (!productDetails) throw new Error("Product folder did not render as a tree");

    expect(productDetails).toHaveAttribute("open");
    expect(
      within(productDetails).getByRole("link", { name: "Sidebar polish notes" })
    ).toBeTruthy();
    expect(
      within(productDetails).getAllByRole("link", { name: "service-matrix.csv" })
    ).toHaveLength(1);
    expect(within(stashes).queryByText("Custom product folder")).toBeNull();
    expect(
      within(stashes).queryByRole("link", { name: "Product/Sidebar polish notes" })
    ).toBeNull();
    expect(
      within(stashes).queryByRole("link", { name: "CSV-backed service matrix" })
    ).toBeNull();
    expect(
      within(stashes).queryByRole("link", { name: "Feature readiness table" })
    ).toBeNull();
  });

  it("keeps an expanded stash open when another stash is clicked", async () => {
    vi.mocked(getWorkspaceSidebar).mockResolvedValue(sidebarWithTwoStashes);

    const first = renderSidebar();

    await screen.findByText("Project Alpha");
    fireEvent.click(screen.getByLabelText("Expand Project Alpha"));
    expect(await screen.findByText("Launch session")).toBeTruthy();

    fireEvent.click(screen.getByRole("link", { name: "Agent Notes" }));
    expect(screen.getByText("Launch session")).toBeTruthy();
    expect(screen.queryByText("Shared session")).toBeNull();
    expect(localStorage.getItem("stash_sidebar_open_stashes")).toBe(
      JSON.stringify({ "ws-1:stash-1": true })
    );

    first.unmount();

    renderSidebar();
    expect(await screen.findByText("Launch session")).toBeTruthy();
    expect(screen.queryByText("Handoff session")).toBeNull();
  });

  it("opens and selects the active session on stash-scoped session item routes", async () => {
    nav.pathname = "/stashes/project-alpha/items/session/session-row-1";
    vi.mocked(getWorkspaceSidebar).mockResolvedValue(sidebarWithStash);

    render(
      <ShareModalProvider>
        <AppSidebar
          user={user}
          activeWorkspaceId="ws-1"
          onCmdkOpen={vi.fn()}
        />
      </ShareModalProvider>
    );

    const sessionLink = await screen.findByRole("link", {
      name: /Planning session/,
    });

    expect(detailsFor("Henry")).toHaveAttribute("open");
    expect(sessionLink).toHaveClass("bg-[var(--color-brand-50)]");
  });

  it("selects Files rows on stash-scoped page and file item routes", async () => {
    vi.mocked(getWorkspaceSidebar).mockResolvedValue(sidebarWithStashFiles);

    for (const row of [
      {
        pathname: "/stashes/project-alpha/items/page/page-root",
        label: "Overview",
      },
      {
        pathname: "/stashes/project-alpha/items/file/file-1",
        label: "Launch brief.md",
      },
      {
        pathname: "/workspaces/ws-1/f/file-csv",
        label: "Launch data.csv",
      },
    ]) {
      cleanup();
      resetStashNavigationCache();
      nav.pathname = row.pathname;
      vi.mocked(getWorkspaceSidebar).mockResolvedValue(sidebarWithStashFiles);

      render(
        <ShareModalProvider>
          <AppSidebar
            user={user}
            activeWorkspaceId="ws-1"
            onCmdkOpen={vi.fn()}
          />
        </ShareModalProvider>
      );

      const fileLink = await screen.findByRole("link", { name: row.label });

      expect(fileLink).toHaveClass("bg-[var(--color-brand-50)]");
    }
  });

  it("opens folders to reveal active nested Files rows on stash item routes", async () => {
    const nestedFile = {
      id: "nested-file",
      workspace_id: "ws-1",
      folder_id: "folder-1",
      name: "Nested brief.md",
      size_bytes: 12,
      content_type: "text/markdown",
      url: null,
      created_at: "2026-05-11T00:00:00Z",
      linked_table_id: null,
    };

    nav.pathname = "/stashes/project-alpha/items/file/nested-file";
    vi.mocked(getWorkspaceSidebar).mockResolvedValue({
      sessions: [],
      files: {
        folders: [
          ...Array.from({ length: 10 }, (_, index) => ({
            id: `filler-folder-${index + 1}`,
            name: `${String(index + 1).padStart(2, "0")} Filler`,
            parent_folder_id: null,
            page_count: 0,
            file_count: 0,
            has_skill: false,
          })),
          {
            id: "folder-1",
            name: "Product Docs",
            parent_folder_id: null,
            page_count: 0,
            file_count: 1,
            has_skill: false,
          },
        ],
        pages: [],
        files: [nestedFile],
      },
      stashes: [
        {
          ...sidebarWithStashFiles.stashes[0],
          item_count: 1,
          items: [
            {
              object_type: "file" as const,
              object_id: "nested-file",
              label_override: "Nested launch file",
              position: 0,
            },
          ],
        },
      ],
    });
    vi.mocked(getFolderContents).mockResolvedValue({
      folder: { id: "folder-1", name: "Product Docs", parent_folder_id: null },
      breadcrumbs: [],
      subfolders: [],
      pages: [],
      files: [nestedFile],
    });

    render(
      <ShareModalProvider>
        <AppSidebar
          user={user}
          activeWorkspaceId="ws-1"
          onCmdkOpen={vi.fn()}
        />
      </ShareModalProvider>
    );

    const fileLink = await screen.findByRole("link", { name: "Nested brief.md" });

    expect(detailsFor("Product Docs")).toHaveAttribute("open");
    expect(fileLink).toHaveClass("bg-[var(--color-brand-50)]");
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

    await waitFor(() => expect(uploadFileOrPage).toHaveBeenCalledWith("ws-1", file));
    expect(await screen.findByText("1 file added.")).toBeTruthy();
  });
});
