import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import AppShell from "./AppShell";
import {
  getCachedWorkspaces,
  readCachedWorkspaces,
} from "../lib/stashNavigationCache";

const nav = vi.hoisted(() => ({
  pathname: "/",
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

vi.mock("./AppSidebar", () => ({
  default: () => <aside data-testid="app-sidebar">Sidebar</aside>,
}));

vi.mock("./CommandPalette", () => ({
  default: () => null,
}));

vi.mock("./ShareModal", () => ({
  default: () => null,
}));

const user = {
  id: "user-1",
  name: "Henry",
  display_name: "Henry",
  description: "",
  created_at: "2026-05-11T00:00:00Z",
  last_seen: "2026-05-11T00:00:00Z",
};

describe("AppShell sidebar collapse", () => {
  beforeEach(() => {
    localStorage.clear();
    nav.pathname = "/";
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
      <AppShell user={user} onLogout={vi.fn()}>
        <div>Page content</div>
      </AppShell>
    );

    fireEvent.click(screen.getByRole("button", { name: "Toggle sidebar" }));

    const main = screen.getByText("Page content").closest("main");
    expect(screen.queryByTestId("app-sidebar")).not.toBeInTheDocument();
    expect(main?.parentElement).toHaveStyle({
      gridTemplateColumns: "minmax(0, 1fr)",
    });
  });
});
