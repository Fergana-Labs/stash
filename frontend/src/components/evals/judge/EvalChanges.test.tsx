import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { expect, it, vi } from "vitest";
import type { EvalChanges as Changes, EvalProposal } from "@/lib/evals-api";
import EvalChanges, { changeTitle } from "./EvalChanges";

// eslint-disable-next-line @next/next/no-img-element -- stands in for the authenticated thumbnail
vi.mock("./FileThumb", () => ({ default: ({ alt }: { alt: string }) => <img alt={alt} /> }));

const tally = (right: number, n: number) => ({ n, right, agreement: n ? right / n : null, good_above_bad: 1 });
const now = new Date().toISOString();
const example = (id: string, extra = {}) => ({
  id, name: "", asked: "", text: `output ${id}`, files: [], label: "bad" as const, note: "", held_out: false, created_at: now,
  added_by_name: "Reviewer", added_via: "web" as const, caller: "", ...extra,
});
const proposal = (extra: Partial<EvalProposal> = {}): EvalProposal => ({
  id: "p2", number: 2, base: 4, status: "open", source: "revised", scoring: "mean", instructions: "",
  traits: [
    { name: "Color", good: "warm red", bad: "blue" },
    { name: "Stripes", good: "plain", bad: "striped" },
    { name: "Size", good: "large", bad: "small" },
  ],
  changes: [
    { kind: "add", trait: "Stripes", why: "the striped ones are bad" },
    { kind: "tighten", trait: "Color", why: "orange passed as red" },
  ],
  before: { number: 4, scoring: "mean", instructions: "", traits: [{ name: "Color", good: "red", bad: "blue" }, { name: "Size", good: "large", bad: "small" }, { name: "Shape", good: "round", bad: "square" }] },
  checks: {
    before: { fit: tally(6, 8), check: tally(3, 4) }, after: { fit: tally(8, 8), check: tally(4, 4) },
    fixed: [{ id: "e1", before: 1, after: 0 }], broke: [], evidence: ["e1", "e2"],
    calls: { n: 10, mean_before: 0.71, mean_after: 0.64, pass_before: 8, pass_after: 7, changed: [{ id: "c1", before: 0.8, after: 0.3 }], calls: [{ id: "c1", before: 0.8, after: 0.3 }] },
    manipulation: { n: 3, resisted: 3, worst: { score: 0.1, base: 0, claim: "" } }, short: null,
  },
  passed: true, quality: { before: { score: 82, parts: {} }, after: { score: 97, parts: {} } },
  proposed_by: null, decided_by: null, decided_at: null, note: "", version: null, stale: false,
  examples: { e1: example("e1", { note: "striped" }), e2: example("e2", { caller: "support-agent" }) },
  calls: { c1: { id: "c1", name: "", asked: "draw a chart", text: "", files: [], caller: "support-agent", created_at: now } },
  created_at: now, ...extra,
});
const show = (proposals: EvalProposal[], onDecide = vi.fn().mockResolvedValue(undefined)) => {
  render(<EvalChanges evalId="e" changes={{ review_required: true, proposals } satisfies Changes} onDecide={onDecide} />);
  return onDecide;
};

it("shows what a proposed change does to the rubric, its checks, and the evidence behind it", () => {
  show([proposal()]);
  const change = screen.getByRole("article", { name: "Change 2" });
  expect(within(change).getByText("Add Stripes, tighten Color")).toBeVisible();
  expect(within(change).getByText("Open")).toBeVisible();

  const rubric = within(change).getByRole("region", { name: "Rubric changes" });
  expect(within(rubric).getByText("the striped ones are bad")).toBeVisible();
  expect(within(rubric).getByText("warm red")).toBeVisible();
  expect(within(rubric).getByText("red")).toBeVisible(); // the wording it replaces
  expect(within(rubric).getByText("Shape")).toBeVisible(); // removed
  expect(within(rubric).getByText("1 trait unchanged")).toBeVisible();

  const checks = within(change).getByRole("region", { name: "Checks" });
  expect(within(checks).getByText("82 → 97")).toBeVisible();
  expect(within(checks).getByText("6/8 → 8/8")).toBeVisible();
  expect(within(checks).getByText("3/4 → 4/4")).toBeVisible();
  expect(within(checks).getByText("8/10 → 7/10")).toBeVisible();
  expect(within(checks).queryByLabelText("Failed")).toBeNull();

  const examples = within(change).getByRole("region", { name: "Examples" });
  expect(within(examples).getByText("1.00 → 0.00")).toBeVisible();
  expect(within(examples).getByText("New since v4")).toBeVisible();
  expect(within(examples).getByText("Reviewer, support-agent")).toBeVisible();
  expect(within(examples).getAllByRole("link")[0]).toHaveAttribute("href", "/reward-models/evals/e/examples/e1");

  const calls = within(change).getByRole("region", { name: "Agent calls" });
  expect(within(calls).getByText("Pass → Fail")).toBeVisible();
  expect(within(calls).getByText("draw a chart")).toBeVisible();
});

it("approves with a note, and offers only an override when a check failed", async () => {
  const onDecide = show([proposal()]);
  fireEvent.change(screen.getByRole("textbox", { name: "Note" }), { target: { value: "matches support" } });
  fireEvent.click(screen.getByRole("button", { name: "Approve" }));
  await waitFor(() => expect(onDecide).toHaveBeenCalledWith("p2", "approve", "matches support"));
});

it("marks a failed check and a change that is out of date", () => {
  const failed = proposal({ passed: false });
  failed.checks!.broke = [{ id: "e2", before: 0.2, after: 0.9 }];
  show([failed, proposal({ id: "p1", number: 1, stale: true })]);
  const change = screen.getByRole("article", { name: "Change 2" });
  expect(within(change).getByLabelText("Failed")).toBeVisible();
  expect(within(change).getByText("Broken")).toBeVisible();
  expect(within(change).getByRole("button", { name: "Approve anyway" })).toBeEnabled();
  expect(within(change).queryByRole("button", { name: "Approve" })).toBeNull();

  const stale = screen.getByRole("article", { name: "Change 1" });
  expect(within(stale).getByText("Out of date")).toBeVisible();
  fireEvent.click(within(stale).getByRole("button", { expanded: false }));
  expect(within(stale).queryByRole("button", { name: /Approve/ })).toBeNull();
  expect(within(stale).getByRole("button", { name: "Reject" })).toBeEnabled();
});

it("waits for checks before approval, and shows a decision once made", () => {
  show([
    proposal({ checks: null, passed: null, quality: { before: null, after: null } }),
    proposal({ id: "p1", number: 1, status: "approved", decided_by: "Reviewer", decided_at: now, version: 5, note: "ok" }),
  ]);
  const waiting = screen.getByRole("article", { name: "Change 2" });
  expect(within(waiting).getByRole("status")).toHaveTextContent("Checking");
  expect(within(waiting).getByRole("button", { name: "Approve" })).toBeDisabled();
  const done = screen.getByRole("article", { name: "Change 1" });
  fireEvent.click(within(done).getByRole("button", { expanded: false }));
  expect(within(done).getByText("by Reviewer")).toBeVisible();
  expect(within(done).getByText("Rubric v5")).toBeVisible();
});

it("says so when nothing is proposed, and titles a change with no trait", () => {
  show([]);
  expect(screen.getByText("No proposed changes")).toBeVisible();
  expect(changeTitle([])).toBe("Rubric change");
  expect(changeTitle([{ kind: "scoring", trait: "the lowest trait", why: "" }])).toBe("Score by the lowest trait");
});
