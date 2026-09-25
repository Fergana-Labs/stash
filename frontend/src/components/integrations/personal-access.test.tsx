import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import IntegrationGate from "./IntegrationGate";
import PersonalSourcesSettings from "@/app/settings/integrations/page";
import SettingsPage from "@/app/settings/page";
import type { Scope, User } from "@/lib/types";

const state = vi.hoisted(() => ({
  scope: null as Scope | null,
  replace: vi.fn(),
  user: {
    id: "existing", name: "existing", display_name: "Existing", description: "",
    created_at: "2026-08-01", last_seen: "2026-09-21",
    developer_platform_only: false, personal_integrations_enabled: true,
  } as User,
}));
vi.mock("next/navigation", () => ({ useRouter: () => ({ replace: state.replace, push: vi.fn() }) }));
vi.mock("@/hooks/useAuth", () => ({
  useAuth: () => ({ user: state.user, loading: false, logout: vi.fn(), refresh: vi.fn() }),
}));
vi.mock("@/lib/scope-store", () => ({ useScope: () => state.scope }));
vi.mock("@/components/developer/DeveloperGate", () => ({
  default: ({ children }: { children: React.ReactNode }) => state.scope?.view === "developer"
    ? <>{children}</> : <div>Developer workspace required</div>,
}));
vi.mock("@/components/workspace/workspace-shell", () => ({
  default: ({ children }: { children: React.ReactNode }) => <>{children}</>,
}));
vi.mock("@/components/integrations/SourceConnectorList", () => ({
  default: ({ returnTo }: { returnTo: string }) => <a href={returnTo}>Manage connections</a>,
}));

beforeEach(() => {
  state.scope = null;
  state.user.personal_integrations_enabled = true;
  state.user.developer_platform_only = false;
  state.replace.mockClear();
});
afterEach(cleanup);

it("preserves the settings entry point for existing personal accounts", () => {
  render(<SettingsPage />);
  expect(screen.getByRole("link", { name: "Sources" })).toHaveAttribute("href", "/settings/integrations");
});

it("hides personal controls from new accounts, including direct navigation", () => {
  state.user.personal_integrations_enabled = false;
  const settings = render(<SettingsPage />);
  expect(screen.queryByRole("link", { name: "Sources" })).not.toBeInTheDocument();
  settings.unmount();
  render(<PersonalSourcesSettings />);
  expect(screen.queryByText("Manage connections")).not.toBeInTheDocument();
  expect(state.replace).toHaveBeenCalledWith("/settings");
});

it("keeps existing connections manageable and returns OAuth to personal settings", () => {
  render(<PersonalSourcesSettings />);
  expect(screen.getByRole("link", { name: "Manage connections" })).toHaveAttribute("href", "/settings/integrations");
});

it("allows the existing account's integration detail page without a developer workspace", () => {
  render(<IntegrationGate>Repository controls</IntegrationGate>);
  expect(screen.getByText("Repository controls")).toBeInTheDocument();
});

it("keeps new personal accounts behind the developer gate", () => {
  state.user.personal_integrations_enabled = false;
  render(<IntegrationGate>Repository controls</IntegrationGate>);
  expect(screen.queryByText("Repository controls")).not.toBeInTheDocument();
  expect(screen.getByText("Developer workspace required")).toBeInTheDocument();
});

it.each([true, false])("preserves developer source access regardless of the personal flag (%s)", (flag) => {
  state.user.personal_integrations_enabled = flag;
  state.scope = { scope_user_id: "workspace", name: "Product", view: "developer" };
  render(<IntegrationGate>Developer source controls</IntegrationGate>);
  expect(screen.getByText("Developer source controls")).toBeInTheDocument();
});

it("does not expose personal controls to developer-only accounts", () => {
  state.user.developer_platform_only = true;
  render(<SettingsPage />);
  expect(screen.queryByRole("link", { name: "Sources" })).not.toBeInTheDocument();
});
