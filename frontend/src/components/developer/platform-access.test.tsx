import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import WorkspaceShell from "@/components/workspace/workspace-shell";
import DeveloperGate from "./DeveloperGate";
import DeveloperSources from "@/app/(app)/developer/sources/page";
import type { Scope } from "@/lib/types";

const state = vi.hoisted(() => ({
  pathname: "/developer",
  scope: null as Scope | null,
  replace: vi.fn(),
  logout: vi.fn(),
  user: {
    id: "user-1", name: "developer", display_name: "Developer", description: "",
    created_at: "2026-09-15", last_seen: "2026-09-15", developer_platform_only: true, personal_integrations_enabled: false,
  },
}));

vi.mock("next/navigation", () => ({
  usePathname: () => state.pathname,
  useSearchParams: () => new URLSearchParams(),
  useRouter: () => ({ replace: state.replace }),
}));
vi.mock("@/hooks/useAuth", () => ({
  useAuth: () => ({ user: state.user, logout: state.logout }),
}));
vi.mock("@/lib/scope-store", () => ({
  useScope: () => state.scope, getScope: () => state.scope, setScope: vi.fn(),
}));
vi.mock("@/lib/api", () => ({
  listMyWorkspaces: async () => [
    { id: "internal", scope_user_id: "internal", name: "Internal team", external_skill_folder_id: null },
    { id: "platform", scope_user_id: "platform", name: "Product", external_skill_folder_id: "skill" },
  ],
  activateDeveloperPlatform: vi.fn(),
}));
vi.mock("@/components/workspace/topbar", () => ({ default: () => <div>Internal navigation</div> }));
vi.mock("@/components/workspace/rail", () => ({ default: () => null }));
vi.mock("@/components/workspace/persistence", () => ({ default: () => null }));
vi.mock("@/components/workspace/explorer", () => ({ default: () => null }));
vi.mock("@/components/workspace/workbench", () => ({ default: () => null }));
vi.mock("@/components/ui/sonner", () => ({ Toaster: () => null }));

vi.mock("@/components/integrations/SourceConnectorList", () => ({
  default: ({ returnTo }: { returnTo: string }) => <a href={returnTo}>Source controls</a>,
}));

beforeEach(() => {
  state.pathname = "/developer";
  state.scope = null;
  state.user.developer_platform_only = true;
  state.replace.mockClear();
  state.logout.mockClear();
});
afterEach(cleanup);

it.each(["/", "/files", "/sessions", "/agents", "/search", "/tools"])(
  "redirects a platform-only account away from %s before internal content mounts",
  (pathname) => {
    state.pathname = pathname;
    render(<WorkspaceShell user={state.user} onLogout={vi.fn()}>Internal content</WorkspaceShell>);
    expect(state.replace).toHaveBeenCalledWith("/developer");
    expect(screen.queryByText("Internal content")).not.toBeInTheDocument();
    expect(screen.queryByText("Internal navigation")).not.toBeInTheDocument();
  },
);

it.each(["/developer", "/developer/users", "/settings"])(
  "uses developer chrome at %s even before a workspace is selected",
  (pathname) => {
    state.pathname = pathname;
    render(<WorkspaceShell user={state.user} onLogout={vi.fn()}>Platform content</WorkspaceShell>);
    expect(screen.getByText("Platform content")).toBeInTheDocument();
    expect(screen.getByLabelText("Stash Developer Platform")).toBeInTheDocument();
    expect(screen.queryByText("Internal navigation")).not.toBeInTheDocument();
    expect(state.replace).not.toHaveBeenCalled();
  },
);

it.each([true, false])("filters context choices according to the account flag (%s)", async (flag) => {
  state.user.developer_platform_only = flag;
  state.scope = { scope_user_id: "platform", name: "Product", view: "developer" };
  render(<WorkspaceShell user={state.user} onLogout={vi.fn()}>Console</WorkspaceShell>);
  await userEvent.click(screen.getByRole("button", { name: "Product Platform" }));
  expect(await screen.findByRole("menuitem", { name: /Product Platform/ })).toBeInTheDocument();
  expect(screen.queryByRole("menuitem", { name: /Personal/ }) !== null).toBe(!flag);
  expect(screen.queryByRole("menuitem", { name: /Internal team/ }) !== null).toBe(!flag);
});

it.each(["/sessions/transcript", "/p/page", "/f/file", "/folders/skill", "/integrations/google"])(
  "keeps the developer platform's shared viewer at %s working in developer chrome",
  async (pathname) => {
    state.pathname = pathname;
    state.scope = { scope_user_id: "platform", name: "Product", view: "developer" };
    render(<WorkspaceShell user={state.user} onLogout={vi.fn()}>Customer content</WorkspaceShell>);
    expect(await screen.findByText("Customer content")).toBeInTheDocument();
    expect(screen.getByLabelText("Stash Developer Platform")).toBeInTheDocument();
    expect(state.replace).not.toHaveBeenCalled();
  },
);

it("requires a developer workspace before showing a shared viewer", async () => {
  state.pathname = "/sessions/transcript";
  render(<WorkspaceShell user={state.user} onLogout={vi.fn()}>Personal content</WorkspaceShell>);
  await screen.findByText("Run Stash for your product's users");
  expect(screen.queryByText("Personal content")).not.toBeInTheDocument();
});

it.each([true, false])("shows the setup exit only for accounts with internal access (%s)", async (flag) => {
  state.user.developer_platform_only = flag;
  render(<DeveloperGate>Console</DeveloperGate>);
  await screen.findByText("Run Stash for your product's users");
  expect(screen.queryByRole("link", { name: /Back to Stash/ }) !== null).toBe(!flag);
});

it("lets a new signup sign out before activating a workspace", async () => {
  render(<DeveloperGate>Console</DeveloperGate>);
  await screen.findByText("Run Stash for your product's users");
  await userEvent.click(screen.getByRole("button", { name: "D" }));
  await userEvent.click(screen.getByRole("button", { name: "Sign out" }));
  expect(state.logout).toHaveBeenCalled();
});

it("preserves existing users' internal interface", async () => {
  state.pathname = "/";
  state.user.developer_platform_only = false;
  render(<WorkspaceShell user={state.user} onLogout={vi.fn()}>Internal content</WorkspaceShell>);
  await waitFor(() => expect(screen.getByText("Internal content")).toBeInTheDocument());
  expect(screen.getByText("Internal navigation")).toBeInTheDocument();
  expect(state.replace).not.toHaveBeenCalled();
});


it("keeps source controls out of personal scope", async () => {
  state.user.developer_platform_only = false;
  render(<DeveloperSources />);
  await screen.findByText("Run Stash for your product's users");
  expect(screen.queryByText("Source controls")).not.toBeInTheDocument();
});

it("opens source management in a developer workspace and returns OAuth there", async () => {
  state.scope = { scope_user_id: "platform", name: "Product", view: "developer" };
  render(<DeveloperSources />);
  expect(await screen.findByRole("link", { name: "Source controls" }))
    .toHaveAttribute("href", "/developer/sources");
});
