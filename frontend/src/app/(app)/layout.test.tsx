import { cleanup, render, screen } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import AppGroupLayout from "./layout";

const route = vi.hoisted(() => ({
  pathname: "/workspaces/ws-1",
  search: "",
  push: vi.fn(),
  auth: {
    user: null as null | {
      id: string;
      name: string;
      display_name: string;
      description: string;
      created_at: string;
      last_seen: string;
    },
    loading: false,
    logout: vi.fn(),
  },
}));

vi.mock("next/navigation", () => ({
  usePathname: () => route.pathname,
  useRouter: () => ({ push: route.push }),
  useSearchParams: () => new URLSearchParams(route.search),
}));

vi.mock("../../components/AppShell", () => ({
  default: ({ children }: { children: ReactNode }) => (
    <div data-testid="app-shell">{children}</div>
  ),
}));

vi.mock("../../components/SkeletonStates", () => ({
  AppShellSkeleton: () => <div data-testid="app-shell-skeleton" />,
  PublicCartridgeSkeleton: () => <div data-testid="public-stash-skeleton" />,
}));

vi.mock("../../hooks/useAuth", () => ({
  useAuth: () => route.auth,
}));

const user = {
  id: "user-1",
  name: "henry",
  display_name: "Henry",
  description: "",
  created_at: "2026-06-08T00:00:00Z",
  last_seen: "2026-06-08T00:00:00Z",
};

describe("AppGroupLayout", () => {
  beforeEach(() => {
    route.pathname = "/workspaces/ws-1";
    route.search = "";
    route.auth = {
      user,
      loading: false,
      logout: vi.fn(),
    };
    route.push.mockClear();
  });

  afterEach(() => {
    cleanup();
  });

  it("keeps normal signed-in app routes inside the app shell", () => {
    render(
      <AppGroupLayout>
        <div>Workspace content</div>
      </AppGroupLayout>,
    );

    expect(screen.getByTestId("app-shell")).toHaveTextContent("Workspace content");
  });

  it("renders workspace Stash item routes without app chrome", () => {
    route.pathname = "/workspaces/ws-1/p/page-1";
    route.search = "stash=shared-stash";

    render(
      <AppGroupLayout>
        <div>Stash item content</div>
      </AppGroupLayout>,
    );

    expect(screen.queryByTestId("app-shell")).not.toBeInTheDocument();
    expect(screen.getByText("Stash item content")).toBeInTheDocument();
  });
});
