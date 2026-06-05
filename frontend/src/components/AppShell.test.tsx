import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import { useMemo, type ReactNode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import AppShell from "./AppShell";
import { BreadcrumbProvider, useBreadcrumbs } from "./BreadcrumbContext";
import { ShellChromeProvider, useShareAction } from "./ShellChromeContext";
import { ShareModalProvider } from "../lib/shareModalContext";
import { getSessionDetail, publishCartridge } from "../lib/api";
import {
  getCachedWorkspaces,
  readCachedWorkspaces,
} from "../lib/stashNavigationCache";

const nav = vi.hoisted(() => ({
  pathname: "/",
}));

const commandPaletteState = vi.hoisted(() => ({
  props: null as {
    open: boolean;
    searchScope: { kind: string; label: string } | null;
  } | null,
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
  getSessionDetail: vi.fn(),
  publishCartridge: vi.fn(),
}));

vi.mock("./AppSidebar", () => ({
  default: () => <aside data-testid="app-sidebar">Sidebar</aside>,
}));

vi.mock("./CommandPalette", () => ({
  default: (props: {
    open: boolean;
    searchScope: { kind: string; label: string } | null;
  }) => {
    commandPaletteState.props = props;
    return props.open ? (
      <div data-testid="command-palette">
        {props.searchScope?.kind}:{props.searchScope?.label}
      </div>
    ) : null;
  },
}));

vi.mock("./CartridgeInviteCenter", () => ({
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

function BreadcrumbPage() {
  useBreadcrumbs(
    [
      { label: "Product", href: "/workspaces/ws-1/folders/folder-1" },
      { label: "Launch plan" },
    ],
    "breadcrumb-page",
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
    vi.mocked(publishCartridge).mockResolvedValue(
      publishedCartridgeResult("shared-link"),
    );
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
      </ShareModalProvider>,
    );

    fireEvent.click(screen.getByRole("button", { name: "Toggle sidebar" }));

    const main = screen.getByText("Page content").closest("main");
    expect(screen.queryByTestId("app-sidebar")).not.toBeInTheDocument();
    expect(main?.parentElement).toHaveStyle({
      gridTemplateColumns: "minmax(0, 1fr)",
    });
  });

  it("restores and persists the resized sidebar width", async () => {
    localStorage.setItem("stash_sidebar_width", "340");

    render(
      <ShareModalProvider>
        <AppShell user={user} onLogout={vi.fn()}>
          <div>Page content</div>
        </AppShell>
      </ShareModalProvider>,
    );

    const grid = screen.getByText("Page content").closest("main")?.parentElement;
    await waitFor(() =>
      expect(grid).toHaveStyle({
        gridTemplateColumns: "340px minmax(0, 1fr)",
      }),
    );

    const handle = screen.getByRole("separator", { name: "Resize sidebar" });
    fireEvent.pointerDown(handle, { button: 0, clientX: 340 });
    fireEvent.pointerMove(window, { clientX: 380 });
    fireEvent.pointerUp(window);

    await waitFor(() =>
      expect(grid).toHaveStyle({
        gridTemplateColumns: "380px minmax(0, 1fr)",
      }),
    );
    expect(localStorage.getItem("stash_sidebar_width")).toBe("380");
  });

  it("shows the signed-in email and signs out from the account menu", () => {
    const onLogout = vi.fn();

    render(
      <ShareModalProvider>
        <AppShell
          user={{ ...user, email: "henry@example.com" }}
          onLogout={onLogout}
        >
          <div>Page content</div>
        </AppShell>
      </ShareModalProvider>,
    );

    fireEvent.click(screen.getByTitle("henry@example.com"));

    expect(screen.getByText("henry@example.com")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("menuitem", { name: "Sign out" }));

    expect(onLogout).toHaveBeenCalledTimes(1);
  });

  it("opens top-bar search with session scope", () => {
    nav.pathname = "/workspaces/ws-1/sessions/session-123";
    mockWorkspaceCache();

    render(
      <ShareModalProvider>
        <AppShell user={user} onLogout={vi.fn()}>
          <div>Session content</div>
        </AppShell>
      </ShareModalProvider>,
    );

    fireEvent.click(screen.getByRole("button", { name: "Search" }));

    expect(screen.getByTestId("command-palette")).toHaveTextContent(
      "session:this session",
    );
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
      </ShareModalProvider>,
    );

    fireEvent.click(await screen.findByRole("button", { name: "Share" }));

    await waitFor(() =>
      expect(publishCartridge).toHaveBeenCalledWith(
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
        { discoverable: false },
      ),
    );
    expect(navigator.clipboard.writeText).toHaveBeenCalledWith(
      "https://app.joinstash.ai/cartridges/shared-link",
    );
  });

  it("creates and copies a one-session Stash link from a session route", async () => {
    nav.pathname = "/workspaces/ws-1/sessions/session-route-id";
    mockWorkspaceCache();
    vi.mocked(getSessionDetail).mockResolvedValue({
      id: "session-row-uuid",
      workspace_id: "ws-1",
      session_id: "session-route-id",
      title: "Debug auth flow",
      agent_name: "codex",
      cwd: null,
      files_touched: [],
      linear_tickets: [],
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
      </ShareModalProvider>,
    );

    fireEvent.click(await screen.findByRole("button", { name: "Share" }));

    await waitFor(() =>
      expect(publishCartridge).toHaveBeenCalledWith(
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
        { discoverable: false },
      ),
    );
    expect(getSessionDetail).toHaveBeenCalledWith("ws-1", "session-route-id");
    expect(navigator.clipboard.writeText).toHaveBeenCalledWith(
      "https://app.joinstash.ai/cartridges/shared-link",
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
      </ShareModalProvider>,
    );

    const home = screen.getByRole("link", { name: "Home" });
    await waitFor(() =>
      expect(home).toHaveAttribute("href", "/workspaces/ws-1"),
    );
    expect(
      screen.queryByRole("button", { name: "Back" }),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByRole("link", { name: "Demo Stash" }),
    ).not.toBeInTheDocument();
  });

  it("hides the default Share action on the workspace home route", async () => {
    nav.pathname = "/workspaces/ws-1";
    mockWorkspaceCache();

    render(
      <ShareModalProvider>
        <AppShell user={user} onLogout={vi.fn()}>
          <div>Workspace content</div>
        </AppShell>
      </ShareModalProvider>,
    );

    await screen.findByText("Workspace content");
    expect(
      screen.queryByRole("button", { name: "Share" }),
    ).not.toBeInTheDocument();
    expect(publishCartridge).not.toHaveBeenCalled();
  });

  it("renders a custom header Share action outside workspace routes", async () => {
    nav.pathname = "/cartridges/shared-stash";
    mockWorkspaceCache();

    function PageWithShareAction() {
      // Memo the node so each re-render registers the same ReactNode identity;
      // otherwise useShareAction's effect re-fires and loops the shell render.
      const shareButton = useMemo(
        () => <button type="button">Share</button>,
        [],
      );
      useShareAction(shareButton);
      return <div>Stash content</div>;
    }

    render(
      <ShellChromeProvider>
        <ShareModalProvider>
          <AppShell user={user} onLogout={vi.fn()}>
            <PageWithShareAction />
          </AppShell>
        </ShareModalProvider>
      </ShellChromeProvider>,
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
      </BreadcrumbProvider>,
    );

    const home = await screen.findByRole("link", { name: "Home" });
    await waitFor(() =>
      expect(home).toHaveAttribute("href", "/workspaces/ws-1"),
    );

    const header = home.closest("header");
    expect(header).not.toBeNull();
    expect(
      within(header!).getByRole("link", { name: "Product" }),
    ).toHaveAttribute("href", "/workspaces/ws-1/folders/folder-1");
    expect(within(header!).getByText("Launch plan")).toBeInTheDocument();
    expect(within(header!).getAllByText("/")).toHaveLength(2);
    expect(
      within(header!).queryByRole("link", { name: "Demo Stash" }),
    ).not.toBeInTheDocument();
  });
});

function publishedCartridgeResult(slug: string) {
  return {
    cartridge: {
      id: "stash-1",
      workspace_id: "ws-1",
      slug,
      title: "Shared link",
      description: "",
      owner_id: "user-1",
      owner_name: "henry",
      owner_display_name: "Henry",
      access: "public" as const,
      workspace_permission: "read" as const,
      public_permission: "read" as const,
      discoverable: false,
      cover_image_url: null,
      icon_url: null,
      view_count: 0,
      items: [],
      is_external: false,
      added_to_workspace_id: null,
      forked_from_cartridge_id: null,
      created_at: "2026-05-11T00:00:00Z",
      updated_at: "2026-05-11T00:00:00Z",
    },
    url: `https://app.joinstash.ai/cartridges/${slug}`,
    cartridge_id: "stash-1",
    cartridge_slug: slug,
  };
}
