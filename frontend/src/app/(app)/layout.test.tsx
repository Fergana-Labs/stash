import { cleanup, render, screen } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import AppGroupLayout from "./layout";

const route = vi.hoisted(() => ({
  pathname: "/",
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

vi.mock("../../components/workspace/workspace-shell", () => ({
  default: ({ children }: { children: ReactNode }) => (
    <div data-testid="app-shell">{children}</div>
  ),
}));

vi.mock("../../components/SkeletonStates", () => ({
  AppShellSkeleton: () => <div data-testid="app-shell-skeleton" />,
  PublicSkillSkeleton: () => <div data-testid="public-skill-skeleton" />,
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
    route.pathname = "/";
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
        <div>App content</div>
      </AppGroupLayout>,
    );

    expect(screen.getByTestId("app-shell")).toHaveTextContent("App content");
  });

  it("renders Skill item deep-link routes without app chrome", () => {
    route.pathname = "/p/page-1";
    route.search = "skill=shared-skill";

    render(
      <AppGroupLayout>
        <div>Skill item content</div>
      </AppGroupLayout>,
    );

    expect(screen.queryByTestId("app-shell")).not.toBeInTheDocument();
    expect(screen.getByText("Skill item content")).toBeInTheDocument();
  });
});
