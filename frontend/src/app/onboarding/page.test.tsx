import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import {
  getOnboardingPreferences,
  getOnboardingStatus,
  putOnboardingPreferences,
  updateMe,
} from "../../lib/api";
import OnboardingPage from "./page";

const navigation = vi.hoisted(() => ({
  push: vi.fn(),
  replace: vi.fn(),
  step: null as string | null,
}));
vi.mock("next/navigation", () => ({
  useRouter: () => navigation,
  useSearchParams: () => new URLSearchParams(navigation.step ? `step=${navigation.step}` : ""),
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
vi.mock("../../components/CopyableCommandBlock", () => ({
  default: ({ commands }: { commands: string }) => <code>{commands}</code>,
}));
vi.mock("../../lib/analytics", () => ({ track: vi.fn() }));
vi.mock("../../lib/api", () => ({
  getOnboardingPreferences: vi.fn(async () => ({ preferences: null })),
  getOnboardingStatus: vi.fn(async () => ({
    curatable_trace_count: 0,
    curatable_session_ids: [],
    skill_count: 0,
    trace_target: 5,
    skill_target: 3,
  })),
  putOnboardingPreferences: vi.fn(async () => ({ ok: true })),
  updateMe: vi.fn(async () => authUser),
}));

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
  navigation.step = null;
  vi.mocked(getOnboardingPreferences).mockResolvedValue({ preferences: null });
  vi.mocked(getOnboardingStatus).mockResolvedValue({
    curatable_trace_count: 0,
    curatable_session_ids: [],
    skill_count: 0,
    trace_target: 5,
    skill_target: 3,
  });
  vi.mocked(putOnboardingPreferences).mockResolvedValue({ ok: true });
  vi.mocked(updateMe).mockResolvedValue(authUser);
});

describe("trace-to-Skills onboarding", () => {
  it("starts with the lightweight About you questions", async () => {
    render(<OnboardingPage />);

    expect(await screen.findByText("First, tell us about you")).toBeInTheDocument();
    expect(screen.getByText("What's your role? Pick as many as fit.")).toBeInTheDocument();
    expect(screen.getByText("How did you hear about us?")).toBeInTheDocument();
    expect(screen.queryByText("Have a hackathon code?")).toBeNull();
    expect(screen.queryByText(/curl -fsSL/)).toBeNull();
    await waitFor(() => expect(putOnboardingPreferences).toHaveBeenCalledOnce());
  });

  it("saves the answers before advancing to connection", async () => {
    render(<OnboardingPage />);
    await screen.findByText("First, tell us about you");

    fireEvent.click(screen.getByRole("button", { name: "Engineer" }));
    fireEvent.click(screen.getByRole("button", { name: "Friend or colleague" }));
    fireEvent.change(screen.getByPlaceholderText(/turn my coding-agent sessions/i), {
      target: { value: "Create reusable debugging skills" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Continue" }));

    await waitFor(() =>
      expect(updateMe).toHaveBeenCalledWith({
        role: "Engineer",
        referral_source: "Friend or colleague",
        use_case: "Create reusable debugging skills",
      }),
    );
    expect(navigation.push).toHaveBeenCalledWith("/onboarding?step=connect");
  });

  it("shows only the CLI action on the connection step", async () => {
    navigation.step = "connect";
    render(<OnboardingPage />);

    expect(await screen.findByText("Connect Stash")).toBeInTheDocument();
    expect(screen.getByText("Stash automatically improves your agent")).toBeInTheDocument();
    expect(screen.getByText("Share with your team")).toBeInTheDocument();
    expect(screen.getByText(/imports only your five most recent sessions/i)).toBeInTheDocument();
    expect(screen.getByText(/curl -fsSL https:\/\/joinstash.ai\/install/)).toBeInTheDocument();
    expect(screen.queryByText(/of 5/)).toBeNull();
  });

  it("lets the user complete onboarding and go Home", async () => {
    navigation.step = "connect";
    render(<OnboardingPage />);

    fireEvent.click(await screen.findByRole("button", { name: "Complete onboarding" }));

    expect(navigation.push).toHaveBeenCalledWith("/");
  });

  it("moves from connection to Home after the first useful session arrives", async () => {
    navigation.step = "connect";
    vi.mocked(getOnboardingStatus).mockResolvedValue({
      curatable_trace_count: 1,
      curatable_session_ids: ["session-1"],
      skill_count: 0,
      trace_target: 5,
      skill_target: 3,
    });

    render(<OnboardingPage />);

    await waitFor(() => expect(navigation.replace).toHaveBeenCalledWith("/"));
  });
});
