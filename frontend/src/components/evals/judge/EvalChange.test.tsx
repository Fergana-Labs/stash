import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { expect, it, vi } from "vitest";
import type { EvalProposal } from "@/lib/evals-api";
import { ChangeView } from "./EvalChange";
import { now, proposal } from "./change-fixture";

// eslint-disable-next-line @next/next/no-img-element -- stands in for the authenticated thumbnail
vi.mock("./FileThumb", () => ({ default: ({ alt }: { alt: string }) => <img alt={alt} /> }));

const show = (p: EvalProposal, tab?: string) => {
  const onDecide = vi.fn().mockResolvedValue(undefined);
  const onComment = vi.fn().mockResolvedValue(undefined);
  render(<ChangeView evalId="e" proposal={p} initialTab={tab} onDecide={onDecide} onComment={onComment} />);
  return { onDecide, onComment };
};
const comment = (extra = {}) => ({ id: "k1", author: "Reviewer", trait: "", body: "too strict?", created_at: now, ...extra });

it("opens on the conversation: how the agent fares under the proposed rubric, the calls that change, and its checks", () => {
  show(proposal({ comments: [comment()] }));
  expect(screen.getByRole("heading", { name: "Add Stripes, tighten Color #2" })).toBeVisible();
  expect(screen.getByText("Open")).toBeVisible();
  expect(screen.getByLabelText("rubric from add-stripes")).toBeVisible();
  expect(screen.getByText("wants to merge 3 edits into", { exact: false })).toBeVisible();
  expect(screen.getByRole("button", { name: /^Conversation\s*1$/ })).toHaveAttribute("aria-current", "page");

  const talk = screen.getByRole("region", { name: "Conversation" });
  expect(within(talk).getByText("opened")).toBeVisible();
  expect(within(talk).getByText("Striped charts now fail on Stripes: 7 of 10 calls pass, down from 8.")).toBeVisible();
  const evals = within(talk).getByRole("table", { name: "Evals" });
  expect(within(evals).getAllByRole("columnheader").map((h) => h.textContent)).toEqual(["Evals", "rubric", "add-stripes", "Change"]);
  expect(within(evals).getByRole("columnheader", { name: "Change" })).toHaveAttribute("aria-sort", "descending");
  const row = within(evals).getAllByRole("row")[1];
  expect(within(row).getAllByRole("cell").map((c) => c.textContent)).toEqual(["draw a chart", "0.80", "0.30", "-0.50"]);
  // Searching narrows the evals by name.
  fireEvent.change(within(evals).getByRole("searchbox", { name: "Search evals" }), { target: { value: "CHART" } });
  expect(within(evals).getByText("draw a chart")).toBeVisible();
  fireEvent.change(within(evals).getByRole("searchbox", { name: "Search evals" }), { target: { value: "memo" } });
  expect(within(evals).queryByText("draw a chart")).toBeNull();
  expect(within(evals).getByText("No evals match")).toBeVisible();
  // The reasons for each edit are on the rubric diff, not here.
  expect(within(talk).queryByText("the striped ones are bad")).toBeNull();
  expect(within(talk).getByText("too strict?")).toBeVisible();
  expect(within(talk).getByText("Checks passed")).toBeVisible();

  // The measurements of the rubric itself are under Checks, not beside the conversation.
  expect(screen.queryByRole("region", { name: "Checks" })).toBeNull();
  // Before-and-after values sit in columns or read "was"; no arrow characters.
  expect(document.body.textContent).not.toMatch(/[→←]|->/);
});

it("merges or closes an open change, with no comment box", async () => {
  const { onDecide } = show(proposal());
  expect(screen.queryByRole("textbox", { name: "Comment" })).toBeNull();
  fireEvent.click(screen.getByRole("button", { name: "Approve and merge" }));
  await waitFor(() => expect(onDecide).toHaveBeenCalledWith("approve", ""));
  fireEvent.click(screen.getByRole("button", { name: "Close" }));
  await waitFor(() => expect(onDecide).toHaveBeenCalledWith("reject", ""));
});

it("shows the rubric before and after, and takes a comment on one trait", async () => {
  const { onComment } = show(proposal({ comments: [comment({ trait: "Stripes", body: "pinstripes too?" })] }), "rubric");
  expect(screen.getByRole("button", { name: /^Rubric changes\s*3$/ })).toHaveAttribute("aria-current", "page");
  const rubric = screen.getByRole("region", { name: "Rubric changes" });
  expect(within(rubric).getByText("the striped ones are bad")).toBeVisible();
  expect(within(rubric).getByText("warm red")).toBeVisible();
  expect(within(rubric).getByText("red")).toBeVisible(); // the wording it replaces
  expect(within(rubric).getByText("Shape")).toBeVisible(); // removed
  expect(within(rubric).getByText("1 trait unchanged")).toBeVisible();
  expect(within(rubric).getByText("pinstripes too?")).toBeVisible();

  fireEvent.click(within(rubric).getByRole("button", { name: "Comment on Color" }));
  fireEvent.change(within(rubric).getByRole("textbox", { name: "Comment on Color" }), { target: { value: "orange is fine" } });
  fireEvent.click(within(rubric).getByRole("button", { name: "Comment" }));
  await waitFor(() => expect(onComment).toHaveBeenCalledWith("orange is fine", "Color"));
});

it("lists the examples the checks point at: broken, fixed, and new since the base version", () => {
  const failed = proposal({ passed: false });
  failed.checks!.broke = [{ id: "e2", before: 0.2, after: 0.9 }];
  show(failed, "checks");
  const checks = screen.getByRole("region", { name: "Checks" });
  expect(within(checks).getAllByRole("columnheader").map((h) => h.textContent)).toEqual(["Checks", "rubric", "add-stripes", ""]);
  expect(within(checks).getByRole("row", { name: /Rubric quality\s*82\s*97/ })).toBeVisible();
  expect(within(checks).getByRole("row", { name: /Agrees with your labels\s*6\/8\s*8\/8/ })).toBeVisible();
  expect(within(checks).getByRole("row", { name: /Agrees with held-out labels\s*3\/4\s*4\/4/ })).toBeVisible();
  expect(within(checks).getByRole("row", { name: /Labeled examples broken\s*1/ })).toBeVisible();
  expect(within(checks).getByRole("row", { name: /Manipulation attempts resisted\s*3\/3/ })).toBeVisible();
  expect(checks).not.toHaveTextContent(/Agent calls passing|Mean score/);
  expect(screen.getByLabelText("Failed")).toBeVisible();
  const examples = screen.getByRole("region", { name: "Examples" });
  expect(within(examples).getByText("Broken")).toBeVisible();
  expect(examples).toHaveTextContent(/0\.00\s*was 1\.00/);
  expect(within(examples).getAllByRole("link")[0]).toHaveAttribute("href", "/reward-models/evals/e/examples/e2");
  expect(within(examples).getByText("Reviewer, support-agent")).toBeVisible();
  expect(screen.queryByRole("table", { name: "Evals" })).toBeNull();
});

it("falls back to the counts when a change has no summary, and lists new examples under Checks", () => {
  const plain = proposal();
  plain.checks!.summary = null;
  plain.checks!.fixed = [];
  const { unmount } = render(<ChangeView evalId="e" proposal={plain} onDecide={vi.fn()} onComment={vi.fn()} />);
  expect(screen.getByText("7 of 10 agent calls pass, 8 before")).toBeVisible();
  unmount();
  show(plain, "checks");
  expect(screen.getByText("New since v4")).toBeVisible();
});

it("offers only an override when a check failed, and no merge when out of date or still checking", () => {
  const { unmount } = render(<ChangeView evalId="e" proposal={proposal({ passed: false })} onDecide={vi.fn()} onComment={vi.fn()} />);
  expect(screen.getByText("Checks failed")).toBeVisible();
  expect(screen.getByRole("button", { name: "Merge anyway" })).toBeEnabled();
  expect(screen.queryByRole("button", { name: "Approve and merge" })).toBeNull();
  unmount();

  const stale = render(<ChangeView evalId="e" proposal={proposal({ stale: true })} onDecide={vi.fn()} onComment={vi.fn()} />);
  expect(screen.getAllByText("Out of date").length).toBeGreaterThan(0);
  expect(screen.queryByRole("button", { name: /merge/i })).toBeNull();
  expect(screen.getByRole("button", { name: "Close" })).toBeEnabled();
  stale.unmount();

  show(proposal({ checks: null, passed: null, quality: { before: null, after: null } }));
  expect(screen.getByText("Checking")).toBeVisible();
  expect(screen.getByRole("button", { name: "Approve and merge" })).toBeDisabled();
});

it("calls a change by its own name when it has one", () => {
  show(proposal({ name: "no-striped-charts" }));
  expect(screen.getByLabelText("rubric from no-striped-charts")).toBeVisible();
});

it("shows a merged change with who merged it, and nothing left to decide", () => {
  show(proposal({
    status: "approved", decided_by: "Reviewer", decided_at: now, version: 5, note: "ok",
    comments: [comment({ created_at: new Date(Date.now() + 60_000).toISOString(), body: "follow up" })],
  }));
  expect(screen.getByText("Merged")).toBeVisible();
  const talk = screen.getByRole("region", { name: "Conversation" });
  expect(within(talk).getByText("merged as rubric v5")).toBeVisible();
  expect(within(talk).getByText("ok")).toBeVisible();
  expect(within(talk).getByText("follow up")).toBeVisible();
  expect(screen.queryByRole("button", { name: "Close" })).toBeNull();
  expect(screen.queryByRole("button", { name: /merge/i })).toBeNull();
  expect(screen.queryByText("Checks passed")).toBeNull();
});
