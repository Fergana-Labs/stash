import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, expect, it, vi } from "vitest";
import { EvalSignals, OutcomeLink } from "./EvalComposition";

const api = vi.hoisted(() => ({ imList: vi.fn(), imEditDraft: vi.fn(), imCredit: vi.fn() }));
vi.mock("@/lib/intuition-api", () => api);
vi.mock("@/components/ui/select", () => ({ Select: ({ value, onChange, options, "aria-label": label }: { value: string; onChange: (v: string) => void; options: { value: string; label: string }[]; "aria-label": string }) => <select aria-label={label} value={value} onChange={(e) => onChange(e.target.value)}>{options.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}</select> }));

const length = { id: "length", type: "score", prompt: "How long?", criteria: ["short", "long"] };
const signal = { id: "eval_tone", type: "eval", prompt: "Decision of the “Tone” eval", criteria: { good: "", bad: "" }, eval_id: "tone", version_id: "tone-v1" };
const detail = (rubric: unknown[]) => ({ model: { id: "reply" }, active: { rubric: [length, signal] }, draft: { rubric } });

beforeEach(() => {
  vi.clearAllMocks();
  api.imList.mockResolvedValue({ models: [{ id: "reply", name: "Reply", active_version_id: "v" }, { id: "tone", name: "Tone", active_version_id: "t" }, { id: "facts", name: "Facts", active_version_id: "f" }, { id: "draft-only", name: "Unsaved", active_version_id: null }] });
  api.imEditDraft.mockResolvedValue({});
});

it("adds a saved eval as a signal and removes an existing one", async () => {
  const changed = vi.fn();
  render(<EvalSignals id="reply" detail={detail([length, signal]) as never} busy={false} onChanged={changed} />);
  const picker = await screen.findByRole("combobox", { name: "Eval to use as a signal" });
  expect(screen.getAllByRole("option").map((o) => o.textContent)).toEqual(["Choose an eval", "Facts"]);
  fireEvent.change(picker, { target: { value: "facts" } });
  fireEvent.click(screen.getByRole("button", { name: "Use" }));
  await waitFor(() => expect(api.imEditDraft).toHaveBeenCalledWith("reply", { rubric: [length, signal, { id: "", type: "eval", prompt: "", criteria: {}, eval_id: "facts" }] }));
  fireEvent.click(screen.getByRole("button", { name: /Stop using Decision of the “Tone” eval/ }));
  await waitFor(() => expect(api.imEditDraft).toHaveBeenLastCalledWith("reply", { rubric: [length] }));
  expect(changed).toHaveBeenCalledTimes(2);
});

it("marks signals that apply on the next Save", async () => {
  const added = { ...signal, id: "eval_facts", prompt: "Decision of the “Facts” eval", eval_id: "facts" };
  render(<EvalSignals id="reply" detail={detail([length, signal, added]) as never} busy={false} onChanged={vi.fn()} />);
  expect(await screen.findByText("applies on Save")).toBeVisible();
  expect(screen.getAllByText(/applies on Save/)).toHaveLength(1);
});

it("shows the learned link between decisions and run outcomes", async () => {
  api.imCredit.mockResolvedValue({ decisions: ["send", "rewrite"], runs: 13, calls: 13, success_rate: 0.46, minimum_runs: 6, by_decision: [{ decision: "send", runs: 7, success_rate: 0.86 }, { decision: "rewrite", runs: 6, success_rate: 0 }], ready: true, weights: [{ decision: "send", weight: 2.1, low: 1.2, high: 3 }, { decision: "rewrite", weight: -2.1, low: -3, high: -1.2 }], cv_accuracy: 0.92, calls_by_credit: [{ prediction_id: "p", run: "r", outcome: 0, decision: "send", credit: 0.8, suspect: true }] });
  render(<OutcomeLink id="reply" />);
  expect(await screen.findByText("86%")).toBeVisible();
  expect(screen.getByText("+2.10")).toBeVisible();
  expect(screen.getByText(/Predicts run outcomes 92% of the time/)).toBeVisible();
  expect(screen.getByText(/1 calls pushed against/)).toBeVisible();
});
