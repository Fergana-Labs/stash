import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, expect, it, vi } from "vitest";
import EvalsPage from "./page";

const api = vi.hoisted(() => ({ list: vi.fn(), sessions: vi.fn(), push: vi.fn() }));
vi.mock("next/navigation", () => ({ useRouter: () => ({ push: api.push }) }));
vi.mock("@/components/BreadcrumbContext", () => ({ useBreadcrumbs: () => {} }));
vi.mock("@/lib/intuition-api", () => ({ imList: api.list }));
vi.mock("@/lib/wizard-api", async (original) => ({ ...await original<typeof import("@/lib/wizard-api")>(), wzSessions: api.sessions }));
beforeEach(() => {
  vi.clearAllMocks();
  api.sessions.mockResolvedValue({ sessions: [] });
  api.list.mockResolvedValue({ models: [{ id: "reply-eval", name: "Replies", active_number: 2, examples: 6, active_metrics: null }] });
});

it("opens the dedicated eval page from the whole row and provides a keyboard-accessible link", async () => {
  render(<EvalsPage />);
  const link = await screen.findByRole("link", { name: "Replies" });
  expect(link).toHaveAttribute("href", "/reward-models/evals/reply-eval");
  fireEvent.click(screen.getByRole("cell", { name: "6" }));
  expect(api.push).toHaveBeenCalledWith("/reward-models/evals/reply-eval");
  expect(screen.queryByRole("columnheader", { name: "Status" })).not.toBeInTheDocument();
  expect(screen.queryByText("Saved", { exact: true })).not.toBeInTheDocument();
  expect(screen.queryByText("Connect")).not.toBeInTheDocument();
  expect(screen.queryByRole("region")).not.toBeInTheDocument();
});


it("never links to the eval-building chat: chat drafts are not listed and unfinished evals open their page", async () => {
  api.list.mockResolvedValue({ models: [{ id: "draft-eval", name: "Slide review", active_number: null, examples: 2, active_metrics: null }] });
  api.sessions.mockResolvedValue({ sessions: [
    { id: "setup", model_id: "draft-eval", title: "Slide review", status: "draft" },
    { id: "early", model_id: null, title: "New model", status: "draft", draft_input: "Check refund policy" },
  ] });
  render(<EvalsPage />);
  expect(await screen.findByRole("link", { name: "Slide review" })).toHaveAttribute("href", "/reward-models/evals/draft-eval");
  expect(screen.queryByText("Check refund policy")).not.toBeInTheDocument();
  expect(api.sessions).not.toHaveBeenCalled();
});
