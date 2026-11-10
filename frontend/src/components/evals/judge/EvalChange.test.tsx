import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { expect, it, vi } from "vitest";
import type { EvalProposal } from "@/lib/evals-api";
import { ChangeView } from "./EvalChange";
import { now, proposal } from "./change-fixture";

// eslint-disable-next-line @next/next/no-img-element -- stands in for the authenticated thumbnail
vi.mock("./FileThumb", () => ({ default: ({ alt }: { alt: string }) => <img alt={alt} /> }));

const show = (p: EvalProposal, tab?: string) => {
  const onDecide = vi.fn().mockResolvedValue(undefined);
  render(<ChangeView proposal={p} initialTab={tab} onDecide={onDecide} />);
  return { onDecide };
};
const comment = (extra = {}) => ({ id: "k1", author: "Reviewer", trait: "", body: "too strict?", created_at: now, ...extra });

it("opens on the conversation: how the agent fares under the proposed rubric and its evals", () => {
  show(proposal({ comments: [comment()] }));
  expect(screen.getByRole("heading", { name: "Add Stripes, tighten Color #2" })).toBeVisible();
  expect(screen.getByText("Open")).toBeVisible();
  expect(screen.getByLabelText("rubric from add-stripes")).toBeVisible();
  expect(screen.getByText("wants to merge 2 edits into", { exact: false })).toBeVisible();
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
  // There are no checks on the page: no tab, no panel, no result line.
  expect(screen.queryByRole("button", { name: /Checks/ })).toBeNull();
  expect(document.body).not.toHaveTextContent(/Checks passed|Agrees with/);
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

it("shows the rubric change as a git-style diff: removed and added lines, numbered, with unchanged lines around them", () => {
  show(proposal(), "rubric");
  expect(screen.getByRole("button", { name: /^Diff\s*\+5 -5$/ })).toHaveAttribute("aria-current", "page");
  const diff = screen.getByRole("region", { name: "Rubric diff" });
  const rows = [...diff.querySelectorAll("[data-kind]")].map((r) => `${r.getAttribute("data-kind")} ${r.textContent}`);
  expect(rows).toEqual([
    "same 11Scored by: Average",
    "same 22",
    "same 33## Color",
    "del 4-Good: red",
    "add 4+Good: warm red",
    "same 55Bad: blue",
    "same 66",
    "add 7+## Stripes",
    "add 8+Good: plain",
    "add 9+Bad: striped",
    "add 10+",
    "same 711## Size",
    "same 812Good: large",
    "same 913Bad: small",
    "del 10-",
    "del 11-## Shape",
    "del 12-Good: round",
    "del 13-Bad: square",
  ]);
  // The reasons for each edit are not part of a diff.
  expect(within(diff).queryByText("the striped ones are bad")).toBeNull();
});

it("falls back to the counts when a change has no summary", () => {
  const plain = proposal();
  plain.checks!.summary = null;
  show(plain);
  expect(screen.getByText("7 of 10 agent calls pass, 8 before")).toBeVisible();
});

it("merges whatever its measurements say, and only closes when out of date", () => {
  const { unmount } = render(<ChangeView proposal={proposal({ passed: false })} onDecide={vi.fn()} />);
  expect(screen.getByRole("button", { name: "Approve and merge" })).toBeEnabled();
  unmount();
  show(proposal({ stale: true }));
  expect(screen.getByText("Out of date")).toBeVisible();
  expect(screen.queryByRole("button", { name: /merge/i })).toBeNull();
  expect(screen.getByRole("button", { name: "Close" })).toBeEnabled();
});

it("shows how the rubric verifier graded both rubrics, trait by trait", () => {
  show(proposal(), "quality");
  expect(screen.getByRole("button", { name: /^Rubric quality\s*0\.75$/ })).toHaveAttribute("aria-current", "page");
  const quality = screen.getByRole("region", { name: "Rubric quality" });
  expect(within(quality).getAllByRole("columnheader").map((h) => h.textContent)).toEqual(["Trait", "rubric", "add-stripes", "Change"]);
  const rows = within(quality).getAllByRole("row").slice(1).map((r) => [...r.children].map((c) => c.textContent));
  expect(rows).toEqual([
    ["Overall", "0.50", "0.75", "+0.25"],
    ["Good and bad are both concreteStripes names plain and striped", "0.50", "1.00", "+0.50"],
    ["One thing per traitColor and Stripes are separate", "0.50", "0.50", "0.00"],
  ]);
});

it("has no Rubric quality tab when the verifier's grade is missing", () => {
  const plain = proposal();
  plain.checks!.rubric_quality = null;
  show(plain);
  expect(screen.queryByRole("button", { name: /Rubric quality/ })).toBeNull();
});

it("sorts the evals by signed change: gains first, no change next, drops last", () => {
  const mixed = proposal();
  const flips = [{ id: "c1", before: 0.5, after: 0.5 }, { id: "c2", before: 1, after: 0.97 }, { id: "c3", before: 0.1, after: 0.9 }];
  mixed.checks!.calls = { ...mixed.checks!.calls!, calls: flips };
  const call = (id: string) => ({ ...mixed.calls.c1, id, asked: id });
  mixed.calls = { c1: call("c1"), c2: call("c2"), c3: call("c3") };
  show(mixed);
  const rows = within(screen.getByRole("table", { name: "Evals" })).getAllByRole("row").slice(1);
  expect(rows.map((r) => within(r).getAllByRole("cell")[3].textContent)).toEqual(["+0.80", "0.00", "-0.03"]);

  // Clicking the heading flips the order, and clicking again flips it back.
  const heading = screen.getByRole("columnheader", { name: "Change" });
  const order = () => within(screen.getByRole("table", { name: "Evals" })).getAllByRole("row").slice(1).map((r) => within(r).getAllByRole("cell")[3].textContent);
  fireEvent.click(within(heading).getByRole("button", { name: "Change" }));
  expect(heading).toHaveAttribute("aria-sort", "ascending");
  expect(order()).toEqual(["-0.03", "0.00", "+0.80"]);
  fireEvent.click(within(heading).getByRole("button", { name: "Change" }));
  expect(order()).toEqual(["+0.80", "0.00", "-0.03"]);

  // Hiding the evals whose score didn't move leaves the other two.
  fireEvent.click(screen.getByRole("switch", { name: "Hide unchanged" }));
  const left = within(screen.getByRole("table", { name: "Evals" })).getAllByRole("row").slice(1);
  expect(left.map((r) => within(r).getAllByRole("cell")[3].textContent)).toEqual(["+0.80", "-0.03"]);
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
});
