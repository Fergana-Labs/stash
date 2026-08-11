// The curator log renders each run's one-sentence learning: the newest run
// leads, the tail hides behind a reveal, and a failed run shows as failed
// instead of vanishing.
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import CuratorLog from "./CuratorLog";
import { getCuratorLog, type CuratorLogEntry } from "@/lib/api";

vi.mock("@/lib/api", () => ({
  getCuratorLog: vi.fn(),
}));

function entry(overrides: Partial<CuratorLogEntry>): CuratorLogEntry {
  return {
    session_id: "agent-curate-cur1-20260808",
    started_at: "2026-08-08T09:00:00Z",
    status: "completed",
    summary: "The eval-harness theme now spans three separate projects.",
    error: null,
    ...overrides,
  };
}

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe("CuratorLog", () => {
  it("shows entries newest first with their summaries", async () => {
    vi.mocked(getCuratorLog).mockResolvedValue({
      entries: [
        entry({ session_id: "run-new", summary: "Newest learning." }),
        entry({
          session_id: "run-old",
          started_at: "2026-08-07T09:00:00Z",
          summary: "Older learning.",
        }),
      ],
    });
    render(<CuratorLog />);
    const entries = await screen.findAllByRole("article");
    expect(entries[0].textContent).toContain("Newest learning.");
    expect(entries[1].textContent).toContain("Older learning.");
  });

  it("collapses the log to five runs with the rest behind a reveal", async () => {
    vi.mocked(getCuratorLog).mockResolvedValue({
      entries: Array.from({ length: 7 }, (_, i) =>
        entry({ session_id: `run-${i}`, summary: `Night ${i}.` })
      ),
    });
    render(<CuratorLog />);
    expect(await screen.findAllByRole("article")).toHaveLength(5);

    fireEvent.click(screen.getByRole("button", { name: "+2 more runs" }));
    expect(screen.getAllByRole("article")).toHaveLength(7);
  });

  it("shows a failed run as failed", async () => {
    vi.mocked(getCuratorLog).mockResolvedValue({
      entries: [entry({ status: "failed", summary: null, error: "credential expired" })],
    });
    render(<CuratorLog />);
    expect(await screen.findByText(/Run failed: credential expired/)).toBeTruthy();
  });

  it("stays honest when no run has happened yet", async () => {
    vi.mocked(getCuratorLog).mockResolvedValue({ entries: [] });
    render(<CuratorLog />);
    expect(await screen.findByText(/No entries yet/)).toBeTruthy();
  });

  // "No entries yet" is a statement about the curator, not about the network:
  // claiming it after a failed load tells the user their curator never ran.
  it("reports a failed load instead of claiming the curator never ran", async () => {
    vi.mocked(getCuratorLog).mockRejectedValue(new Error("curator log unavailable"));
    render(<CuratorLog />);
    expect(await screen.findByText(/curator log unavailable/)).toBeTruthy();
    expect(screen.queryByText(/No entries yet/)).toBeNull();
  });
});
