import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import AppShell from "./AppShell";
import { BreadcrumbProvider, useBreadcrumbs } from "./BreadcrumbContext";
import { ShareModalProvider } from "../lib/shareModalContext";
import {
  getCachedWorkspaces,
  readCachedWorkspaces,
} from "../lib/stashNavigationCache";

const nav = vi.hoisted(() => ({
  pathname: "/",
  back: vi.fn(),
}));

const commandPaletteState = vi.hoisted(() => ({
  props: null as { open: boolean; searchScope: { kind: string; label: string } | null } | null,
}));

vi.mock("next/navigation", () => ({
  usePathname: () => nav.pathname,
  useRouter: () => ({ back: nav.back }),
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
    nav.back.mockClear();
    commandPaletteState.props = null;
    vi.clearAllMocks();
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
    expect(screen.queryByRole("link", { name: "Demo Stash" })).not.toBeInTheDocument();
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
