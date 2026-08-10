import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import OnboardingPage from "./page";
import { updateMe } from "../../lib/api";

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
vi.mock("../../lib/analytics", () => ({ track: vi.fn() }));
vi.mock("../../lib/api", () => ({
  createMyKey: vi.fn(),
  createPage: vi.fn(),
  getAgentApiKey: vi.fn(),
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

  it("there is no plan question — role and referral are the only requirements", () => {
    render(<OnboardingPage />);
    expect(screen.queryByText("Which plan fits you?")).toBeNull();
  });
});

// Roles are multi-answer. A pre-seed founder who also writes the code is both,
// and forcing one pill made the very first question in the product feel wrong
// to the first investor who tried it.
describe("role is multi-select", () => {
  it("takes more than one answer and sends them all", async () => {
    render(<OnboardingPage />);
    const engineer = screen.getByRole("button", { name: "Engineer" });
    const founder = screen.getByRole("button", { name: "Founder / Exec" });

    fireEvent.click(engineer);
    fireEvent.click(founder);
    expect(engineer).toHaveAttribute("aria-pressed", "true");
    expect(founder).toHaveAttribute("aria-pressed", "true");

    fireEvent.click(screen.getByRole("button", { name: "Search" }));
    fireEvent.click(screen.getByRole("button", { name: "Continue" }));

    await waitFor(() =>
      expect(updateMe).toHaveBeenCalledWith(
        expect.objectContaining({ role: "Engineer, Founder / Exec" }),
      ),
    );
  });

  it("keeps referral single-select — you heard about us one way", () => {
    render(<OnboardingPage />);
    const search = screen.getByRole("button", { name: "Search" });
    const github = screen.getByRole("button", { name: "GitHub" });

    fireEvent.click(search);
    fireEvent.click(github);

    expect(search).toHaveAttribute("aria-pressed", "false");
    expect(github).toHaveAttribute("aria-pressed", "true");
  });

  it("will not send a bare \"Other\" — it has to be spelled out", () => {
    render(<OnboardingPage />);
    fireEvent.click(screen.getAllByRole("button", { name: "Other" })[0]);
    fireEvent.click(screen.getByRole("button", { name: "Search" }));

    const continueButton = screen.getByRole("button", { name: "Continue" });
    expect(continueButton).toBeDisabled();

    fireEvent.change(screen.getByPlaceholderText("What's your role?"), {
      target: { value: "Founding engineer" },
    });
    expect(continueButton).toBeEnabled();
  });
});
