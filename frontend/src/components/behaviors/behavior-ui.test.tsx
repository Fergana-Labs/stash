import { render, screen } from "@testing-library/react";
import { expect, it } from "vitest";
import { BehaviorChips, cleanSnippet, groupBySession, hourlyBuckets, integerTicks } from "./behavior-ui";
import { judgeHeadline } from "@/components/agent-judge/TraceJudgePanel";
import { humanize, type SearchResult } from "@/lib/behaviors-api";

it("uses integer ticks so low counts never repeat a label", () => {
  expect(integerTicks(0)).toEqual([0, 1]);
  expect(integerTicks(2)).toEqual([0, 1, 2]);
  expect(integerTicks(9)).toEqual([0, 3, 6, 9]);
});

it("buckets hits by hour over the range", () => {
  const now = Date.UTC(2026, 0, 2, 12);
  const buckets = hourlyBuckets([now - 30 * 60_000, now - 90 * 60_000, now - 10 * 86_400_000], 1, now);
  expect(buckets).toHaveLength(24);
  expect(buckets.reduce((n, b) => n + b.hits, 0)).toBe(2);
});

it("humanizes enum values and strips transcript prefixes from snippets", () => {
  expect(humanize("partial_answer")).toBe("Partial answer");
  expect(humanize("no_signal")).toBe("No signal");
  expect(cleanSnippet("steps 2–5: [1] USER where is my refund [2] ASSISTANT It was sent")).toBe("where is my refund It was sent");
});

it("dedupes behavior chips with a count and caps them at three", () => {
  const b = (behavior_id: string, name: string, start_idx: number) => ({ id: `${behavior_id}-${start_idx}`, behavior_id, name, actor: "agent" as const, start_idx, end_idx: start_idx, review: null, confidence: null });
  render(<BehaviorChips traceId="t" behaviors={[b("a", "Loop", 1), b("a", "Loop", 5), b("b", "Error", 2), b("c", "Retry", 3), b("d", "Stall", 4)]} />);
  expect(screen.getByText("×2")).toBeInTheDocument();
  expect(screen.getByText("+1")).toBeInTheDocument();
  expect(screen.queryByText("Stall")).not.toBeInTheDocument();
});

it("groups results that share a session, keeping singletons in place", () => {
  const r = (trace_id: string, session_id: string | null) => ({ trace_id, session_id }) as SearchResult;
  const groups = groupBySession([r("1", "s"), r("2", null), r("3", "s"), r("4", "x")]);
  expect(groups.map((g) => [g.session, g.rows.map((x) => x.trace_id)])).toEqual([["s", ["1", "3"]], [null, ["2"]], [null, ["4"]]]);
});

it("headlines a claims check by counts, not a probability", () => {
  const claim = (status: string) => ({ id: status + Math.random(), text: "", step_idx: null, status, evidence: [], external: [] });
  const report = (statuses: string[]) => ({ status: "done", report: { claims: statuses.map(claim) } }) as never;
  expect(judgeHeadline(report(["verified", "contradicted", "verified"])).text).toBe("1 of 3 claims contradicted");
  expect(judgeHeadline(report(["verified", "verified"])).text).toBe("All 2 claims verified");
});
