// The first-run screen and the moment it stops being true.
//
// A brand-new stash is usually a stash mid-arrival: the user has just run the
// installer and their history is uploading in the background. On a customer
// call this exact gap read as "I don't know what changed or what happened" —
// the page kept telling him to run a command he had already run. So the empty
// state has to watch for the first transcript and get out of the way by
// itself, without a reload.
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import BrainDashboard from "./BrainDashboard";
import { getMe, getMeOverview } from "@/lib/api";

vi.mock("@/lib/api", () => ({
  getMe: vi.fn(),
  getMeOverview: vi.fn(),
  getEmbeddingProjection: vi.fn(),
  getMemoryGraph: vi.fn(),
  listFileActivity: vi.fn(),
}));

vi.mock("@/components/viz/EmbeddingSpaceExplorer", () => ({ default: () => null }));
vi.mock("@/components/memory/CuratorLog", () => ({ default: () => null }));
vi.mock("@/components/memory/WikiGraph", () => ({ default: () => null }));
vi.mock("@/components/CopyableCommandBlock", () => ({
  default: ({ commands }: { commands: string }) => <pre>{commands}</pre>,
}));

const EMPTY = { pages: 0, files: 0, sessions: 0 };

beforeEach(async () => {
  const api = await import("@/lib/api");
  vi.mocked(getMe).mockResolvedValue({ display_name: "Henry Dowling" } as never);
  vi.mocked(api.listFileActivity).mockResolvedValue({ events: [], has_more: false } as never);
  vi.mocked(api.getEmbeddingProjection).mockResolvedValue({ points: [] } as never);
  vi.mocked(api.getMemoryGraph).mockResolvedValue({ nodes: [], edges: [] } as never);
});

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
  vi.useRealTimers();
});

describe("first-run state", () => {
  it("asks for transcripts while the stash is empty", async () => {
    vi.mocked(getMeOverview).mockResolvedValue(EMPTY);

    render(<BrainDashboard />);

    expect(await screen.findByText("Let's get you started")).toBeInTheDocument();
    // It must not read as a dead end to someone who already ran the installer.
    expect(screen.getByText(/Already ran it\?/)).toBeInTheDocument();
  });

  it("gets out of the way once the first transcript lands, with no reload", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    vi.mocked(getMeOverview)
      .mockResolvedValueOnce(EMPTY)
      .mockResolvedValue({ pages: 0, files: 0, sessions: 1 });

    render(<BrainDashboard />);
    await screen.findByText("Let's get you started");

    await vi.advanceTimersByTimeAsync(6000);

    await waitFor(() =>
      expect(screen.queryByText("Let's get you started")).not.toBeInTheDocument(),
    );
    expect(await screen.findByText(/Welcome back/)).toBeInTheDocument();
  });

  it("does not poll once there is something to show", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    vi.mocked(getMeOverview).mockResolvedValue({ pages: 3, files: 0, sessions: 0 });

    render(<BrainDashboard />);
    await screen.findByText(/Welcome back/);

    const callsAfterLoad = vi.mocked(getMeOverview).mock.calls.length;
    await vi.advanceTimersByTimeAsync(30000);
    expect(vi.mocked(getMeOverview).mock.calls.length).toBe(callsAfterLoad);
  });
});
