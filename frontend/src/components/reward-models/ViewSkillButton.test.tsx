import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { toast } from "sonner";
import { rmCreateGepaRun, rmListGepaRuns } from "@/lib/api";
import type { RmGepaRun } from "@/lib/types";
import ViewSkillButton from "./ViewSkillButton";

const { push } = vi.hoisted(() => ({ push: vi.fn() }));
vi.mock("next/navigation", () => ({ useRouter: () => ({ push }) }));
vi.mock("sonner", () => ({ toast: { error: vi.fn() } }));
vi.mock("@/lib/api", () => ({ rmCreateGepaRun: vi.fn(), rmListGepaRuns: vi.fn() }));

beforeEach(() => vi.clearAllMocks());

describe("View skill", () => {
  it("starts generation only when requested and only if the model has no skill run", async () => {
    vi.mocked(rmListGepaRuns).mockResolvedValue([]);
    vi.mocked(rmCreateGepaRun).mockResolvedValue({ id: "new-run" } as RmGepaRun);
    render(<ViewSkillButton modelId="model" />);
    expect(rmListGepaRuns).not.toHaveBeenCalled();
    expect(rmCreateGepaRun).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", { name: "View skill" }));
    await waitFor(() => expect(push).toHaveBeenCalledWith("/reward-models/gepa/new-run"));
    expect(rmCreateGepaRun).toHaveBeenCalledExactlyOnceWith({ reward_model_id: "model" });
  });

  it.each(["queued", "running", "succeeded", "failed"] as const)("reopens a %s run without spending another generation", async (status) => {
    vi.mocked(rmListGepaRuns).mockResolvedValue([
      { id: "other", reward_model_id: "another-model", status: "succeeded" },
      { id: "existing", reward_model_id: "model", status },
    ] as RmGepaRun[]);
    render(<ViewSkillButton modelId="model" />);
    fireEvent.click(screen.getByRole("button", { name: "View skill" }));
    await waitFor(() => expect(push).toHaveBeenCalledWith("/reward-models/gepa/existing"));
    expect(rmCreateGepaRun).not.toHaveBeenCalled();
  });

  it("reports a failed lookup instead of creating a potentially duplicate skill", async () => {
    vi.mocked(rmListGepaRuns).mockRejectedValue(new Error("Connection lost"));
    render(<ViewSkillButton modelId="model" />);
    fireEvent.click(screen.getByRole("button", { name: "View skill" }));
    await waitFor(() => expect(toast.error).toHaveBeenCalledWith("Connection lost"));
    expect(rmCreateGepaRun).not.toHaveBeenCalled();
    expect(push).not.toHaveBeenCalled();
    expect(screen.getByRole("button", { name: "View skill" })).toBeEnabled();
  });
});
