import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, expect, it, vi } from "vitest";
import EvalsPage from "./page";

const api = vi.hoisted(() => ({ list: vi.fn(), sessions: vi.fn(), push: vi.fn(), judged: vi.fn() }));
vi.mock("@/lib/evals-api", () => ({ evalList: api.judged }));
vi.mock("next/navigation", () => ({ useRouter: () => ({ push: api.push }) }));
vi.mock("@/components/BreadcrumbContext", () => ({ useBreadcrumbs: () => {} }));
vi.mock("@/lib/intuition-api", () => ({ imList: api.list }));
vi.mock("@/lib/wizard-api", async (original) => ({ ...await original<typeof import("@/lib/wizard-api")>(), wzSessions: api.sessions }));
beforeEach(() => {
  vi.clearAllMocks();
  api.sessions.mockResolvedValue({ sessions: [] });
  api.judged.mockResolvedValue([]);
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

it("links each eval that reviews its rubric changes to its changes, with how many are open", async () => {
  const judged = (id: string, extra: object) => ({ id, name: id, instructions: "", ready: true, build: null, examples: { good: 3, bad: 3 }, review_required: false, open_changes: 0, ...extra });
  api.list.mockResolvedValue({ models: ["emails", "quiet", "plain"].map((id) => ({ id, name: id, active_number: 1, examples: 6, active_metrics: null })) });
  api.judged.mockResolvedValue([judged("emails", { review_required: true, open_changes: 2 }), judged("quiet", { review_required: true }), judged("plain", {})]);
  render(<EvalsPage />);
  expect(await screen.findByRole("columnheader", { name: "Change requests" })).toBeVisible();
  const open = screen.getByRole("link", { name: "2 open change requests to emails" });
  expect(open).toHaveAttribute("href", "/reward-models/evals/emails?tab=changes");
  expect(open).toHaveTextContent("2 open");
  expect(screen.getByRole("link", { name: "0 open change requests to quiet" })).toHaveAttribute("href", "/reward-models/evals/quiet?tab=changes");
  // An eval that doesn't review its changes shows nothing in the column.
  expect(screen.queryByRole("link", { name: /open change requests? to plain/ })).toBeNull();
  // Clicking the count goes to the changes, not to the eval's first tab.
  fireEvent.click(open);
  expect(api.push).not.toHaveBeenCalled();
});
