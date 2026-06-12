import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import OnboardingPage from "./page";

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
  useSearchParams: () => new URLSearchParams(),
}));

const authUser = vi.hoisted(() => ({
  id: "user-1",
  name: "Henry",
  display_name: "Henry",
  description: "",
  created_at: "2026-05-31T00:00:00Z",
  last_seen: "2026-05-31T00:00:00Z",
}));

vi.mock("../../hooks/useAuth", () => ({
  useAuth: () => ({ user: authUser, loading: false, logout: vi.fn() }),
}));

vi.mock("../../components/Header", () => ({ default: () => null }));
vi.mock("../../components/integrations/SourceConnectorList", () => ({
  default: () => null,
}));
vi.mock("./paths/memory/MemoryAskStep", () => ({ default: () => null }));
vi.mock("../../lib/analytics", () => ({ track: vi.fn() }));
vi.mock("../../lib/api", () => ({
  createPage: vi.fn(),
  getAgentApiKey: vi.fn(),
  listMyWorkspaces: vi.fn().mockResolvedValue({ workspaces: [] }),
  updateMe: vi.fn(),
  updatePage: vi.fn(),
}));

afterEach(cleanup);

describe("about step pills", () => {
  it("clicking a selected pill unselects it, so a mis-click is recoverable", () => {
    render(<OnboardingPage />);
    const pill = screen.getByRole("button", { name: "Engineer" });

    fireEvent.click(pill);
    expect(pill).toHaveAttribute("aria-pressed", "true");

    fireEvent.click(pill);
    expect(pill).toHaveAttribute("aria-pressed", "false");
  });

  it("unselecting a required answer disables Continue again", () => {
    render(<OnboardingPage />);
    const role = screen.getByRole("button", { name: "Engineer" });
    const referral = screen.getByRole("button", { name: "Search" });
    const continueButton = screen.getByRole("button", { name: "Continue" });

    fireEvent.click(role);
    fireEvent.click(referral);
    expect(continueButton).toBeEnabled();

    fireEvent.click(role);
    expect(continueButton).toBeDisabled();
  });
});
