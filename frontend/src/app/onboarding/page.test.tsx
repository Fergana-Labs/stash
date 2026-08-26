import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import OnboardingPage from "./page";
import { getOnboardingPreferences, putOnboardingPreferences, updateMe } from "../../lib/api";

// Mutable so a test can render a later step (?step=N) directly.
const searchParams = vi.hoisted(() => ({ current: new URLSearchParams() }));

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
  useSearchParams: () => searchParams.current,
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
  getClaudeMdBlock: vi.fn(async () => ({ block: "<!-- stash-context -->\n## Stash\n…" })),
  getOnboardingPreferences: vi.fn(async () => ({ preferences: null })),
  putOnboardingPreferences: vi.fn(async () => ({ ok: true })),
  updateMe: vi.fn(),
  updatePage: vi.fn(),
}));

afterEach(() => {
  cleanup();
  searchParams.current = new URLSearchParams();
  vi.mocked(getOnboardingPreferences).mockImplementation(async () => ({ preferences: null }));
  vi.mocked(putOnboardingPreferences).mockImplementation(async () => ({ ok: true }));
});

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

// The setup step is the point of the flow: choices made here are stored
// server-side and applied by `stash signin`, so the terminal asks nothing.
describe("setup step", () => {
  it("preselects sane defaults: all agents, record everywhere, import and CLAUDE.md on", () => {
    searchParams.current = new URLSearchParams("step=2");
    render(<OnboardingPage />);

    expect(screen.getByRole("button", { name: "Claude Code" })).toHaveAttribute(
      "aria-pressed",
      "true",
    );
    expect(screen.getByRole("radio", { name: /Everywhere on this machine/ })).toHaveAttribute(
      "aria-checked",
      "true",
    );
    expect(
      screen.getByRole("checkbox", { name: /Import my past agent conversations/ }),
    ).toHaveAttribute("aria-checked", "true");
    expect(
      screen.getByRole("checkbox", { name: /Add Stash instructions to my repo's CLAUDE.md/ }),
    ).toHaveAttribute("aria-checked", "true");
  });

  it("stores the edited choices server-side on Continue — that's what the CLI applies", async () => {
    searchParams.current = new URLSearchParams("step=2");
    render(<OnboardingPage />);

    fireEvent.click(screen.getByRole("button", { name: "Cursor" }));
    fireEvent.click(screen.getByRole("radio", { name: /Only a folder I pick/ }));
    fireEvent.click(screen.getByRole("button", { name: "Continue" }));

    await waitFor(() =>
      expect(putOnboardingPreferences).toHaveBeenCalledWith({
        enabled_agents: ["claude", "codex", "opencode", "gemini", "openclaw", "hermes"],
        record_scope: "selected_folders",
        import_history: true,
        claude_md_opt_in: true,
      }),
    );
  });

  it("a failed save blocks the flow — the connect step must not promise unsaved choices", async () => {
    searchParams.current = new URLSearchParams("step=2");
    vi.mocked(putOnboardingPreferences).mockImplementation(async () => {
      throw new Error("server said no");
    });
    render(<OnboardingPage />);

    fireEvent.click(screen.getByRole("button", { name: "Continue" }));

    await waitFor(() => expect(screen.getByText("server said no")).toBeInTheDocument());
    // Still on the setup step, not the connect step.
    expect(screen.queryByText("Now connect your agent")).toBeNull();
  });

  it("shows the exact CLAUDE.md block, served by the backend so it can't drift", async () => {
    searchParams.current = new URLSearchParams("step=2");
    render(<OnboardingPage />);

    fireEvent.click(screen.getByRole("button", { name: "Show exactly what gets appended" }));

    await waitFor(() =>
      expect(screen.getByText(/<!-- stash-context -->/)).toBeInTheDocument(),
    );
  });
});

describe("connect step copy", () => {
  it("promises no questions only when choices are actually stored", async () => {
    searchParams.current = new URLSearchParams("step=3");
    vi.mocked(getOnboardingPreferences).mockImplementation(async () => ({
      preferences: {
        enabled_agents: ["claude"],
        record_scope: "everything",
        import_history: false,
        claude_md_opt_in: false,
        consumed_at: null,
      },
    }));
    render(<OnboardingPage />);

    await waitFor(() =>
      expect(
        screen.getByText(/Applies the choices you made here, printing each one\. No questions\./),
      ).toBeInTheDocument(),
    );
  });

  it("with folder scope, says the terminal still asks the one folder question", async () => {
    searchParams.current = new URLSearchParams("step=3");
    vi.mocked(getOnboardingPreferences).mockImplementation(async () => ({
      preferences: {
        enabled_agents: ["claude"],
        record_scope: "selected_folders",
        import_history: false,
        claude_md_opt_in: false,
        consumed_at: null,
      },
    }));
    render(<OnboardingPage />);

    await waitFor(() =>
      expect(
        screen.getByText(/Asks the one question a browser can't answer/),
      ).toBeInTheDocument(),
    );
  });

  it("without stored choices, falls back to honest copy: the terminal asks", async () => {
    searchParams.current = new URLSearchParams("step=3");
    render(<OnboardingPage />);

    await waitFor(() =>
      expect(
        screen.getByText(/Asks its setup questions in the terminal/),
      ).toBeInTheDocument(),
    );
  });
});
