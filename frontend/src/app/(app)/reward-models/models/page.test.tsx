import { render, screen } from "@testing-library/react";
import { expect, it, vi } from "vitest";
import ModelsPage from "./page";
import { ProductCheckpointProvider } from "@/components/ProductCheckpointContext";

vi.mock("../evals/page", () => ({ default: () => <h1>Evals</h1> }));
vi.mock("@/components/reward-models/LegacyRewardModels", () => ({ default: () => <h1>Legacy model view</h1> }));

it("opens evals from the old model-list URL", () => {
  render(<ModelsPage />);
  expect(screen.getByRole("heading", { name: "Evals" })).toBeVisible();
  expect(screen.queryByText("Legacy model view")).not.toBeInTheDocument();
});

it("preserves the explicitly pinned product checkpoint", () => {
  render(<ProductCheckpointProvider checkpoint="floodgate-2026-10-05"><ModelsPage /></ProductCheckpointProvider>);
  expect(screen.getByRole("heading", { name: "Legacy model view" })).toBeVisible();
});
