import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, expect, it, vi } from "vitest";
import { ImprovePanel, LabelQueue, VersionsPanel } from "./EvalLearning";

const api = vi.hoisted(() => ({ imGet: vi.fn(), imImproveStatus: vi.fn(), imStartImprove: vi.fn(), imPromote: vi.fn(), imLabelQueue: vi.fn(), imReview: vi.fn(), imRestore: vi.fn() }));
vi.mock("@/lib/intuition-api", () => api);

const polite = { id: "polite", type: "noul", prompt: "Is it polite?", criteria: { true: "Yes", false: "No" } };
const length = { id: "length", type: "score", prompt: "How long?", criteria: ["short", "long"] };
const gate = { passed: true, checks: [], incumbent: null, active_version: 1 };
const detail = {
  model: { id: "eval", name: "Replies", output_type: "choice" },
  active: { number: 1, rubric: [length] },
  draft: { number: 2, rubric: [length, polite], gate },
  versions: [
    { id: "v2", number: 2, status: "draft", metrics: null, gate: null, has_head: true, created_at: "2026-10-13T00:00:00Z", promoted_at: null },
    { id: "v1", number: 1, status: "active", metrics: { eval: { n: 4, accuracy: 0.75 } }, gate: null, has_head: true, created_at: "2026-10-12T00:00:00Z", promoted_at: "2026-10-12T00:00:00Z" },
    { id: "v0", number: 0, status: "retired", metrics: null, gate: { forced: true }, has_head: true, created_at: "2026-10-11T00:00:00Z", promoted_at: "2026-10-11T00:00:00Z" },
  ],
};
const job = {
  id: "job", model_id: "eval", status: "succeeded", progress: {}, error: null, created_at: "", finished_at: "",
  result: {
    base_version: 1, winner: "add_question", changed: true, gate, held_out: { n: 4, accuracy: 1, log_loss: 0.2 },
    candidates: [
      { name: "current", title: "Current criteria", rationale: "", questions: 1, new_questions: [], rubric: [length], cv_log_loss: 0.69, cv_accuracy: 0.5, rows: 12 },
      { name: "add_question", title: "Add a question for its mistakes", rationale: "", questions: 2, new_questions: ["Is it polite?"], rubric: [length, polite], cv_log_loss: 0.2, cv_accuracy: 0.92, rows: 12 },
    ],
  },
};

beforeEach(() => vi.clearAllMocks());

it("shows the winning criteria and applies them through the gate", async () => {
  api.imImproveStatus.mockResolvedValue({ job });
  api.imPromote.mockResolvedValue(detail);
  const changed = vi.fn();
  render(<ImprovePanel id="eval" detail={detail as never} examples={[]} busy={false} onChanged={changed} />);
  expect(await screen.findByText("Add a question for its mistakes")).toBeVisible();
  expect(screen.getByText("92%")).toBeVisible();
  expect(screen.getByText("Is it polite?")).toBeVisible();
  fireEvent.click(screen.getByRole("button", { name: "Apply improved criteria" }));
  await waitFor(() => expect(api.imPromote).toHaveBeenCalledWith("eval", false));
  expect(changed).toHaveBeenCalled();
});

it("starts an improvement and reports progress while it runs", async () => {
  api.imImproveStatus.mockResolvedValue({ job: null });
  api.imStartImprove.mockResolvedValue({ ...job, status: "running", result: null, progress: { message: "Answering criteria", completed: 3, total: 10 } });
  render(<ImprovePanel id="eval" detail={detail as never} examples={[]} busy={false} onChanged={vi.fn()} />);
  fireEvent.click(await screen.findByRole("button", { name: "Improve" }));
  expect(await screen.findByText("Answering criteria 3/10")).toBeVisible();
  expect(screen.getByRole("button", { name: "Improving…" })).toBeDisabled();
});

it("lists past versions and restores a retired one", async () => {
  api.imRestore.mockResolvedValue(detail);
  const changed = vi.fn();
  render(<VersionsPanel id="eval" detail={detail as never} busy={false} onChanged={changed} />);
  expect(screen.getByText("75% held-out")).toBeVisible();
  expect(screen.getByText("override")).toBeVisible();
  expect(screen.queryByText("v2")).not.toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Restore" }));
  await waitFor(() => expect(api.imRestore).toHaveBeenCalledWith("eval", "v0"));
  expect(changed).toHaveBeenCalledWith(detail);
});

it("labels the calls worth labeling and explains why each was picked", async () => {
  api.imLabelQueue.mockResolvedValueOnce([{ prediction_id: "p1", kind: "predict", input: { item: "Maybe later" }, predicted: "good", confidence: 0.55, ref: "t-1", caller: "api", version: 1, created_at: "", uncertainty: 0.9, novelty: 0.1, conflict: true, score: 1.5, reasons: ["outcome feedback says bad", "the eval was unsure"] }]).mockResolvedValue([]);
  api.imReview.mockResolvedValue({});
  const labeled = vi.fn();
  render(<LabelQueue id="eval" labels={["good", "bad"]} onLabeled={labeled} />);
  expect(await screen.findByText("outcome feedback says bad")).toBeVisible();
  fireEvent.click(screen.getByRole("button", { name: "Mark bad" }));
  await waitFor(() => expect(api.imReview).toHaveBeenCalledWith("eval", "p1", { label: "bad" }));
  expect(labeled).toHaveBeenCalled();
});
