import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import AppShell from "./AppShell";
import { BreadcrumbProvider, useBreadcrumbs } from "./BreadcrumbContext";
import { ShareModalProvider } from "../lib/shareModalContext";
import {
  apiFetch,
  createInviteToken,
  getMe,
  getSessionDetail,
  getWorkspaceMembers,
  publishStash,
} from "../lib/api";
import {
  getCachedWorkspaces,
  readCachedWorkspaces,
} from "../lib/stashNavigationCache";

const nav = vi.hoisted(() => ({
  pathname: "/",
}));

const commandPaletteState = vi.hoisted(() => ({
  props: null as { open: boolean; searchScope: { kind: string; label: string } | null } | null,
}));

vi.mock("next/navigation", () => ({
  usePathname: () => nav.pathname,
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

vi.mock("../lib/stashNavigationCache", () => ({
  getCachedWorkspaces: vi.fn(),
  readCachedWorkspaces: vi.fn(),
}));

vi.mock("../lib/api", () => ({
  apiFetch: vi.fn(),
  createInviteToken: vi.fn(),
  getMe: vi.fn(),
  getSessionDetail: vi.fn(),
  getWorkspaceMembers: vi.fn(),
  publishStash: vi.fn(),
}));

vi.mock("./AppSidebar", () => ({
  default: () => <aside data-testid="app-sidebar">Sidebar</aside>,
}));

vi.mock("./CommandPalette", () => ({
  default: (props: { open: boolean; searchScope: { kind: string; label: string } | null }) => {
    commandPaletteState.props = props;
    return props.open ? (
      <div data-testid="command-palette">
        {props.searchScope?.kind}:{props.searchScope?.label}
      </div>
    ) : null;
  },
}));

vi.mock("./StashInviteCenter", () => ({
  default: () => <button aria-label="Stash invites">Invites</button>,
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
  creator_id: user.id,
  invite_code: "invite",
  created_at: "2026-05-11T00:00:00Z",
  updated_at: "2026-05-11T00:00:00Z",
  member_count: 1,
};

const workspaceMember = {
  user_id: user.id,
  name: user.name,
  display_name: user.display_name,
  role: "owner",
  joined_at: "2026-05-11T00:00:00Z",
};

function BreadcrumbPage() {
  useBreadcrumbs(
    [
      { label: "Product", href: "/workspaces/ws-1/folders/folder-1" },
      { label: "Launch plan" },
    ],
    "breadcrumb-page"
  );

  return <div>Page content</div>;
}

function mockWorkspaceCache() {
  const cache = {
    userId: user.id,
    all: [workspace],
    mine: [],
    shared: [],
  };
  vi.mocked(readCachedWorkspaces).mockReturnValue(cache);
  vi.mocked(getCachedWorkspaces).mockResolvedValue(cache);
}

describe("AppShell sidebar collapse", () => {
  beforeEach(() => {
    localStorage.clear();
    nav.pathname = "/";
    commandPaletteState.props = null;
    vi.clearAllMocks();
    Object.defineProperty(navigator, "clipboard", {
      configurable: true,
      value: { writeText: vi.fn().mockResolvedValue(undefined) },
    });
    vi.mocked(publishStash).mockResolvedValue(publishedStashResult("shared-link"));
    vi.mocked(apiFetch).mockResolvedValue({});
    vi.mocked(createInviteToken).mockResolvedValue({
      id: "invite-1",
      token: "invite-token",
      workspace_id: "ws-1",
      expires_at: "2026-05-18T00:00:00Z",
    });
    vi.mocked(getMe).mockResolvedValue(user);
    vi.mocked(getWorkspaceMembers).mockResolvedValue([workspaceMember]);
    vi.mocked(readCachedWorkspaces).mockReturnValue({
      userId: user.id,
      all: [],
      mine: [],
      shared: [],
    });
    vi.mocked(getCachedWorkspaces).mockResolvedValue({
      userId: user.id,
      all: [],
      mine: [],
      shared: [],
    });
  });

  afterEach(() => {
    cleanup();
  });

  it("keeps page content in the visible grid column when collapsed", () => {
    render(
      <ShareModalProvider>
        <AppShell user={user} onLogout={vi.fn()}>
          <div>Page content</div>
        </AppShell>
      </ShareModalProvider>
    );

    fireEvent.click(screen.getByRole("button", { name: "Toggle sidebar" }));

    const main = screen.getByText("Page content").closest("main");
    expect(screen.queryByTestId("app-sidebar")).not.toBeInTheDocument();
    expect(main?.parentElement).toHaveStyle({
      gridTemplateColumns: "minmax(0, 1fr)",
    });
  });

  it("opens top-bar search with session scope", () => {
    nav.pathname = "/workspaces/ws-1/sessions/session-123";
    mockWorkspaceCache();

    render(
      <ShareModalProvider>
        <AppShell user={user} onLogout={vi.fn()}>
          <div>Session content</div>
        </AppShell>
      </ShareModalProvider>
    );

    fireEvent.click(screen.getByRole("button", { name: "Search" }));

    expect(screen.getByTestId("command-palette")).toHaveTextContent("session:this session");
    expect(commandPaletteState.props?.searchScope?.kind).toBe("session");
  });

  it("creates and copies a one-page Stash link from a page route", async () => {
    nav.pathname = "/workspaces/ws-1/p/page-1";
    mockWorkspaceCache();

    render(
      <ShareModalProvider>
        <AppShell user={user} onLogout={vi.fn()}>
          <div>Page content</div>
        </AppShell>
      </ShareModalProvider>
    );

    fireEvent.click(await screen.findByRole("button", { name: "Share" }));

    await waitFor(() =>
      expect(publishStash).toHaveBeenCalledWith(
        "ws-1",
        "Shared page",
        [
          {
            object_type: "page",
            object_id: "page-1",
            position: 0,
            label_override: "Shared page",
          },
        ],
        { discoverable: false }
      )
    );
    expect(navigator.clipboard.writeText).toHaveBeenCalledWith(
      "https://app.joinstash.ai/stashes/shared-link"
    );
  });

  it("creates and copies a one-session Stash link from a session route", async () => {
    nav.pathname = "/workspaces/ws-1/sessions/session-route-id";
    mockWorkspaceCache();
    vi.mocked(getSessionDetail).mockResolvedValue({
      id: "session-row-uuid",
      workspace_id: "ws-1",
      session_id: "session-route-id",
      agent_name: "codex",
      cwd: null,
      summary: "Debug auth flow. Confirm token expiry.",
      summary_status: "done",
      files_touched: [],
      started_at: null,
      finished_at: null,
      created_by: "user-1",
      artifacts: [],
    });

    render(
      <ShareModalProvider>
        <AppShell user={user} onLogout={vi.fn()}>
          <div>Session content</div>
        </AppShell>
      </ShareModalProvider>
    );

    fireEvent.click(await screen.findByRole("button", { name: "Share" }));

    await waitFor(() =>
      expect(publishStash).toHaveBeenCalledWith(
        "ws-1",
        "Debug auth flow",
        [
          {
            object_type: "session",
            object_id: "session-row-uuid",
            position: 0,
            label_override: "Debug auth flow",
          },
        ],
        { discoverable: false }
      )
    );
    expect(getSessionDetail).toHaveBeenCalledWith("ws-1", "session-route-id");
    expect(navigator.clipboard.writeText).toHaveBeenCalledWith(
      "https://app.joinstash.ai/stashes/shared-link"
    );
  });

  it("keeps Home clickable on the workspace home route", async () => {
    nav.pathname = "/workspaces/ws-1";
    mockWorkspaceCache();

    render(
      <ShareModalProvider>
        <AppShell user={user} onLogout={vi.fn()}>
          <div>Workspace content</div>
        </AppShell>
      </ShareModalProvider>
    );

    const home = screen.getByRole("link", { name: "Home" });
    await waitFor(() => expect(home).toHaveAttribute("href", "/workspaces/ws-1"));
    expect(screen.queryByRole("button", { name: "Back" })).not.toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "Demo Stash" })).not.toBeInTheDocument();
  });

  it("opens workspace sharing as a dropdown on the workspace home route", async () => {
    nav.pathname = "/workspaces/ws-1";
    mockWorkspaceCache();

    render(
      <ShareModalProvider>
        <AppShell user={user} onLogout={vi.fn()}>
          <div>Workspace content</div>
        </AppShell>
      </ShareModalProvider>
    );

    fireEvent.click(await screen.findByRole("button", { name: "Share" }));

    const dialog = await screen.findByRole("dialog", { name: "Share Demo Stash" });
    expect(dialog).toBeInTheDocument();
    await within(dialog).findByText("Henry");
    fireEvent.click(within(dialog).getByRole("button", { name: "Generate invite link" }));
    await waitFor(() => expect(createInviteToken).toHaveBeenCalledWith("ws-1", 5, 7));
    expect(
      within(dialog).getByDisplayValue(`${window.location.origin}/join/invite-token`)
    ).toBeInTheDocument();
    expect(publishStash).not.toHaveBeenCalled();
  });

  it("renders a custom header Share action outside workspace routes", async () => {
    nav.pathname = "/stashes/shared-stash";
    mockWorkspaceCache();

    render(
      <ShareModalProvider>
        <AppShell
          user={user}
          onLogout={vi.fn()}
          shareAction={<button type="button">Share</button>}
        >
          <div>Stash content</div>
        </AppShell>
      </ShareModalProvider>
    );

    const share = await screen.findByRole("button", { name: "Share" });
    expect(share.closest("header")).not.toBeNull();
  });

  it("renders breadcrumbs as a Home-rooted file path", async () => {
    nav.pathname = "/workspaces/ws-1/p/page-1";
    mockWorkspaceCache();

    render(
      <BreadcrumbProvider>
        <ShareModalProvider>
          <AppShell user={user} onLogout={vi.fn()}>
            <BreadcrumbPage />
          </AppShell>
        </ShareModalProvider>
      </BreadcrumbProvider>
    );

    const home = await screen.findByRole("link", { name: "Home" });
    await waitFor(() => expect(home).toHaveAttribute("href", "/workspaces/ws-1"));

    const header = home.closest("header");
    expect(header).not.toBeNull();
    expect(within(header!).getByRole("link", { name: "Product" })).toHaveAttribute(
      "href",
      "/workspaces/ws-1/folders/folder-1"
    );
    expect(within(header!).getByText("Launch plan")).toBeInTheDocument();
    expect(within(header!).getAllByText("/")).toHaveLength(2);
    expect(within(header!).queryByRole("link", { name: "Demo Stash" })).not.toBeInTheDocument();
  });
});

function publishedStashResult(slug: string) {
  return {
    stash: {
      id: "stash-1",
      workspace_id: "ws-1",
      slug,
      title: "Shared link",
      description: "",
      owner_id: "user-1",
      owner_name: "henry",
      owner_display_name: "Henry",
      access: "public",
      discoverable: false,
      cover_image_url: null,
      icon_url: null,
      view_count: 0,
      items: [],
      is_external: false,
      added_to_workspace_id: null,
      forked_from_stash_id: null,
      created_at: "2026-05-11T00:00:00Z",
      updated_at: "2026-05-11T00:00:00Z",
    },
    url: `https://app.joinstash.ai/stashes/${slug}`,
    stash_id: "stash-1",
    stash_slug: slug,
  };
}
