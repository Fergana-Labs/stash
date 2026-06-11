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
import {
  ShellChromeProvider,
  useActiveWorkspaceId,
  useShareAction,
} from "./ShellChromeContext";
import { ShareModalProvider } from "../lib/shareModalContext";
import {
  getCachedWorkspaces,
  readCachedWorkspaces,
} from "../lib/skillNavigationCache";

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

vi.mock("../lib/skillNavigationCache", () => ({
  getCachedWorkspaces: vi.fn(),
  readCachedWorkspaces: vi.fn(),
}));

// Stands in for a detail client (PageClient / SessionClient): canonical item
// URLs carry no workspace, so the client publishes the loaded resource's
// workspace to the shell.
function PublishActiveWorkspace({ id }: { id: string }) {
  useActiveWorkspaceId(id);
  return null;
}

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

vi.mock("./SkillInviteCenter", () => ({
  default: () => <button aria-label="Skill invites">Invites</button>,
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
  name: "Demo Skill",
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

  it("shows the signed-in email, username, and signs out from the account menu", () => {
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
    expect(screen.getByText("@Henry")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("menuitem", { name: "Sign out" }));

    expect(onLogout).toHaveBeenCalledTimes(1);
  });

  it("opens top-bar search with session scope", () => {
    nav.pathname = "/sessions/session-123";
    mockWorkspaceCache();

    render(
      <ShellChromeProvider>
        <ShareModalProvider>
          <AppShell user={user} onLogout={vi.fn()}>
            <PublishActiveWorkspace id="ws-1" />
            <div>Session content</div>
          </AppShell>
        </ShareModalProvider>
      </ShellChromeProvider>,
    );

    fireEvent.click(screen.getByRole("button", { name: "Search" }));

    expect(screen.getByTestId("command-palette")).toHaveTextContent(
      "session:this session",
    );
    expect(commandPaletteState.props?.searchScope?.kind).toBe("session");
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
      screen.queryByRole("link", { name: "Demo Skill" }),
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
  });

  it.each([
    "/f/file-1",
    "/p/page-1",
    "/sessions/session-route-id",
    "/workspaces/ws-1/folders/folder-1",
  ])("does not render a default Share action on %s", async (pathname) => {
    nav.pathname = pathname;
    mockWorkspaceCache();

    render(
      <ShellChromeProvider>
        <ShareModalProvider>
          <AppShell user={user} onLogout={vi.fn()}>
            <PublishActiveWorkspace id="ws-1" />
            <div>File content</div>
          </AppShell>
        </ShareModalProvider>
      </ShellChromeProvider>,
    );

    await screen.findByText("File content");
    expect(
      screen.queryByRole("button", { name: "Share" }),
    ).not.toBeInTheDocument();
  });

  it("renders a custom header Share action outside workspace routes", async () => {
    nav.pathname = "/skills/shared-skill";
    mockWorkspaceCache();

    function PageWithShareAction() {
      // Memo the node so each re-render registers the same ReactNode identity;
      // otherwise useShareAction's effect re-fires and loops the shell render.
      const shareButton = useMemo(
        () => <button type="button">Share</button>,
        [],
      );
      useShareAction(shareButton);
      return <div>Skill content</div>;
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
      within(header!).queryByRole("link", { name: "Demo Skill" }),
    ).not.toBeInTheDocument();
  });
});
