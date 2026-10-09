import { expect, it } from "vitest";
import type { RmTraceSummary } from "@/lib/types";
import { matchesTraceFilters, traceSourceKey, traceSourceName } from "./trace-sources";

it("uses inclusive local calendar dates, including both ends of the last day", () => {
  const trace = { source_id: "codex", source_owner_id: "henry" } as RmTraceSummary;
  const filters = { source: "henry/codex", from: "2026-10-08", through: "2026-10-09" };
  for (const date of [new Date(2026, 9, 8, 0, 0), new Date(2026, 9, 9, 23, 59, 59)]) {
    expect(matchesTraceFilters({ ...trace, created_at: date.toISOString() }, filters)).toBe(true);
  }
  for (const date of [new Date(2026, 9, 7, 23, 59), new Date(2026, 9, 10, 0, 0)]) {
    expect(matchesTraceFilters({ ...trace, created_at: date.toISOString() }, filters)).toBe(false);
  }
  expect(matchesTraceFilters({ ...trace, created_at: "invalid" }, filters)).toBe(false);
});

it("keeps identical source IDs from different owners separate and supports old summaries", () => {
  const trace = { source_id: "codex", source_owner_id: "henry", source_name: "Henry’s Codex" } as RmTraceSummary;
  expect(matchesTraceFilters(trace, { source: "sam/codex", from: "", through: "" })).toBe(false);
  expect(traceSourceKey(trace)).toBe("henry/codex");
  expect(traceSourceName(trace)).toBe("Henry’s Codex");
  expect(traceSourceName({ agent: "claude_code" } as RmTraceSummary)).toBe("Claude Code");
});
