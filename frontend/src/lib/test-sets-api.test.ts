import { expect, it } from "vitest";
import { effectiveBaseline, inputPreview, parseCasesJsonl, runDelta, type RunRow, type RunSummary } from "./test-sets-api";

it("previews a conversation by its last user message and the turns before it", () => {
  expect(inputPreview("Where is order 9120?")).toEqual({ text: "Where is order 9120?", earlier: 0 });
  expect(inputPreview([
    { role: "user", content: "Hi" }, { role: "assistant", content: "Hello" }, { role: "user", content: "Refund please" },
  ])).toEqual({ text: "Refund please", earlier: 2 });
});

it("parses JSONL cases and names the bad line", () => {
  expect(parseCasesJsonl('{"name":"a","input":"q","expected":"x"}\n\n{"input":[{"role":"user","content":"q2"}]}\n')).toEqual([
    { name: "a", input: "q", expected: "x" },
    { name: undefined, input: [{ role: "user", content: "q2" }], expected: null },
  ]);
  expect(() => parseCasesJsonl('{"input":"ok"}\nnot json')).toThrow("Line 2 is not valid JSON");
  expect(() => parseCasesJsonl('{"expected":"x"}')).toThrow('Line 1 needs an "input"');
});

it("compares a run with its baseline, and falls back to the latest run that passed", () => {
  const summary = (pass_rate: number, base: number | null): RunSummary => ({
    cases: 3, passed: 2, pass_rate, errors: 0, scorers: {}, baseline: base === null ? null : { pass_rate: base, cases: 3 }, broke: [], fixed: [], gate: "pass",
  });
  expect(runDelta(summary(2 / 3, 1))).toBeCloseTo(-1 / 3);
  expect(runDelta(summary(1, null))).toBeNull();
  const run = (id: string, status: RunRow["status"], gate: "pass" | "fail" = "pass"): RunRow => ({ id, label: id, status, error: null, baseline_run_id: null, summary: status === "done" ? { ...summary(1, null), gate } : null, created_at: "", finished_at: null });
  const runs = [run("v4", "scoring"), run("v3", "done", "fail"), run("v2", "done"), run("v1", "done")];
  expect(effectiveBaseline({ baseline_run_id: null, runs })).toBe("v2");
  expect(effectiveBaseline({ baseline_run_id: "v1", runs })).toBe("v1");
});
