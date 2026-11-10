import { fireEvent, render, screen, within } from "@testing-library/react";
import { expect, it } from "vitest";
import type { EvalChanges as Changes, EvalProposal } from "@/lib/evals-api";
import EvalChanges, { changeTitle } from "./EvalChanges";
import { now, proposal } from "./change-fixture";

const show = (proposals: EvalProposal[]) => render(<EvalChanges evalId="e" changes={{ review_required: true, proposals } satisfies Changes} />);
const comment = { id: "k1", author: "Reviewer", trait: "", body: "too strict?", created_at: now };

it("lists open changes, each linking to its own page with its comments", () => {
  show([
    proposal({ comments: [comment, { ...comment, id: "k2" }] }),
    proposal({ id: "p1", number: 1, status: "approved", version: 5, decided_by: "Reviewer", decided_at: now }),
  ]);
  expect(screen.getByRole("button", { name: "1 Open" })).toHaveAttribute("aria-pressed", "true");
  const rows = screen.getAllByRole("link");
  expect(rows).toHaveLength(1);
  expect(rows[0]).toHaveAttribute("href", "/reward-models/evals/e/changes/2");
  expect(within(rows[0]).getByText("Add Stripes, tighten Color")).toBeVisible();
  expect(within(rows[0]).getByTitle("Comments")).toHaveTextContent("2");
  expect(within(rows[0]).getByText("Owner")).toBeVisible();
});

it("lists merged and closed changes under Closed", () => {
  show([
    proposal(),
    proposal({ id: "p1", number: 1, status: "approved", version: 5, decided_by: "Reviewer", decided_at: now }),
    proposal({ id: "p0", number: 0, status: "rejected", passed: false, decided_by: "Reviewer", decided_at: now }),
  ]);
  fireEvent.click(screen.getByRole("button", { name: "2 Closed" }));
  const rows = screen.getAllByRole("link");
  expect(rows.map((r) => r.getAttribute("href"))).toEqual(["/reward-models/evals/e/changes/1", "/reward-models/evals/e/changes/0"]);
  expect(within(rows[0]).getByText("Merged as v5")).toBeVisible();
  expect(within(rows[1]).getByText("Closed")).toBeVisible();
});

it("marks a change that is out of date, and opens on Closed when nothing is open", () => {
  const { unmount } = show([proposal({ checks: null, passed: null }), proposal({ id: "p1", number: 1, stale: true })]);
  expect(screen.getByText("Out of date")).toBeVisible();
  unmount();
  show([proposal({ status: "rejected" })]);
  expect(screen.getByRole("button", { name: "1 Closed" })).toHaveAttribute("aria-pressed", "true");
});

it("says so when nothing is proposed, and titles a change with no trait", () => {
  show([]);
  expect(screen.getByText("No open change requests")).toBeVisible();
  expect(changeTitle([])).toBe("Rubric change");
  expect(changeTitle([{ kind: "scoring", trait: "the lowest trait", why: "" }])).toBe("Score by the lowest trait");
});
