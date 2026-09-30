import { fireEvent, render, screen } from "@testing-library/react";
import { expect, it, vi } from "vitest";
import { rmListRewardModels } from "@/lib/api";
import type { RmRewardModel } from "@/lib/types";
import RewardModelsPage from "./page";

vi.mock("next/navigation", () => ({ useRouter: () => ({ push: vi.fn() }) }));
vi.mock("@/components/BreadcrumbContext", () => ({ useBreadcrumbs: vi.fn() }));
vi.mock("@/components/reward-models/TrainSheet", () => ({ default: () => null }));
vi.mock("@/components/reward-models/FeedbackDialog", () => ({ default: () => null }));
vi.mock("@/components/reward-models/ViewSkillButton", () => ({ default: () => null }));
vi.mock("@/components/reward-models/RmSkeletons", () => ({
  RmListSkeleton: () => <div role="status">Loading models</div>,
}));
vi.mock("@/lib/api", () => ({ rmListRewardModels: vi.fn() }));

it("replaces failed loading with an error and lets the user recover without reloading", async () => {
  vi.mocked(rmListRewardModels)
    .mockRejectedValueOnce(new Error("Internal server error"))
    .mockResolvedValueOnce([{
      id: "model", name: "My reward model", status: "failed", trace_count: 13,
      created_at: new Date().toISOString(), base_model: "Qwen/Qwen3-0.6B",
      compute: "modal", epochs: 1, metrics: null, error: null,
    } as RmRewardModel]);

  render(<RewardModelsPage />);
  expect(await screen.findByRole("alert")).toHaveTextContent("Internal server error");
  expect(screen.queryByRole("status")).not.toBeInTheDocument();
  expect(screen.queryByText("No reward models yet")).not.toBeInTheDocument();

  fireEvent.click(screen.getByRole("button", { name: "Try again" }));
  expect(await screen.findByText("My reward model")).toBeVisible();
  expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  expect(rmListRewardModels).toHaveBeenCalledTimes(2);
});
