import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, expect, it, vi } from "vitest";
import EvalsPage from "./page";

const api = vi.hoisted(() => ({ list: vi.fn(), push: vi.fn() }));
vi.mock("next/navigation", () => ({ useRouter: () => ({ push: api.push }) }));
vi.mock("@/components/BreadcrumbContext", () => ({ useBreadcrumbs: () => {} }));
vi.mock("@/lib/intuition-api", () => ({ imList: api.list }));
beforeEach(() => {
  vi.clearAllMocks();
  api.list.mockResolvedValue({ models: [{ id: "reply-eval", name: "Replies", active_number: 2, examples: 6, active_metrics: null }] });
});

it("opens the dedicated eval page from the whole row and provides a keyboard-accessible link", async () => {
  render(<EvalsPage />);
  const link = await screen.findByRole("link", { name: "Replies" });
  expect(link).toHaveAttribute("href", "/reward-models/evals/reply-eval");
  fireEvent.click(screen.getByRole("cell", { name: "Saved" }));
  expect(api.push).toHaveBeenCalledWith("/reward-models/evals/reply-eval");
  expect(screen.queryByText("Connect")).not.toBeInTheDocument();
  expect(screen.queryByRole("region")).not.toBeInTheDocument();
});
