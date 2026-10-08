import { render, screen } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import type { RmStep } from "@/lib/types";
import type { TraceEvaluation, TraceEvaluationResponse } from "@/lib/workbench-api";
import { automaticActionScores, automaticAnnotationProgress } from "./automatic-credit";
import TraceMinimap from "./TraceMinimap";

const steps: RmStep[] = [0, 1, 2].map((index) => ({ id: String(index), index, role: "assistant", content: "Response", tool_name: null, tool_input: null, tool_call_id: null, metadata: null }));
const credit = (step_id: string, value: number | null) => ({ step_id, index: Number(step_id), credit: value, label: "positive", confidence: 1, call_id: "call" });
const saved = [credit("0", 1), credit("1", 2)].map((c) => ({ ...c, evaluation_id: "previous", created_at: "2026-10-07" }));
const response = (current: TraceEvaluationResponse["current"]) => ({ current, previous_credits: saved }) as TraceEvaluationResponse;

beforeEach(() => { vi.stubGlobal("ResizeObserver", class { observe() {} disconnect() {} }); });
afterEach(() => vi.unstubAllGlobals());

it("retains bar heights while the trace grows and current scores arrive in batches", () => {
  const scroller = { current: document.createElement("div") }, navigation = { current: document.createElement("div") };
  const old = { status: "completed", created_at: "2026-10-07", credits: saved } as unknown as TraceEvaluation;
  const props = { steps, annotations: [], scroller, navigation, onJump: vi.fn() };
  const view = render(<TraceMinimap {...props} actionScores={automaticActionScores(response(old), steps)} />);
  expect(screen.getByRole("button", { name: "Step 2: Response, credit +1.00" }).lastElementChild).toHaveStyle({ height: "46px" });
  view.rerender(<TraceMinimap {...props} actionScores={automaticActionScores(response(null), steps)} annotationStatus="Updating annotations · previous values retained" />);
  expect(screen.getByRole("button", { name: "Step 2: Response, credit +1.00, previous annotation" }).lastElementChild).toHaveStyle({ height: "46px" });
  expect(screen.getByRole("status")).toHaveTextContent("previous values retained");
  expect(screen.getByRole("button", { name: "Step 3: Response, awaiting score" }).lastElementChild).toHaveStyle({ height: "6px" });
  const partial = { ...old, status: "running", credits: [credit("0", -1)] };
  view.rerender(<TraceMinimap {...props} actionScores={automaticActionScores(response(partial), steps)} />);
  expect(screen.getByRole("button", { name: "Step 1: Response, credit -0.50" }).lastElementChild).toHaveStyle({ height: "16px" });
  expect(screen.getByRole("button", { name: "Step 2: Response, credit +1.00, previous annotation" }).lastElementChild).toHaveStyle({ height: "46px" });
});

it("lets uncertain current results supersede old scores and never applies scores to other steps", () => {
  const current = { status: "running", created_at: "2026-10-07", credits: [credit("0", null)] } as TraceEvaluation;
  expect([...automaticActionScores(response(current), steps).keys()]).toEqual(["1"]);
  expect(automaticActionScores(response(null), [{ ...steps[0], id: "replacement" }]).size).toBe(0);
  expect(automaticActionScores(response({ ...current, status: "completed" }), steps).size).toBe(0);
});

it("counts only gradable actions and distinguishes previous, pending, and uncertain annotations", () => {
  const mixed = [...steps, { ...steps[0], id: "new-action" },
    { ...steps[0], id: "user", role: "user" },
    { ...steps[0], id: "tool", role: "tool" },
    { ...steps[0], id: "thinking", metadata: { thinking: true } },
    { ...steps[0], id: "empty", content: " " }] as RmStep[];
  const data = { ...response({ status: "running", credits: [credit("0", null)] } as TraceEvaluation), configured: true, boundary: { kind: "completed_response", step_index: 3 }, queue: { status: "queued", error: "Invalid response" } };
  const progress = automaticAnnotationProgress(data, mixed, automaticActionScores(data, mixed));
  expect(progress.label).toBe("1 of 4 actions scored · 1 previous · 2 awaiting scores · 1 with insufficient evidence · Retrying annotation update…");
  expect([...progress.unscoredReasons]).toEqual([["0", "insufficient evidence"], ["2", "awaiting score"], ["new-action", "awaiting score"]]);
});

it("reports a failed update even when there are no previous scores", () => {
  const data = { ...response(null), previous_credits: [], configured: true, queue: { status: "failed", error: "Invalid response" } };
  expect(automaticAnnotationProgress(data, steps, automaticActionScores(data, steps)).label).toBe("0 of 3 actions scored · 3 awaiting scores · Annotation update failed");
});

it("uses continuous expected credit for current and previous bar heights without rounding to labels", () => {
  const data = response({ status: "running", created_at: "2026-10-07", credits: [{ ...credit("0", 1), expected_credit: 0.35 }] } as TraceEvaluation);
  data.previous_credits = saved.map((c) => ({ ...c, expected_credit: 0.7 }));
  const scores = automaticActionScores(data, steps);
  expect(scores.get("0")?.credit).toBe(0.35);
  expect(scores.get("1")?.credit).toBe(0.7);
  render(<TraceMinimap steps={steps} annotations={[]} actionScores={scores} scroller={{ current: null }} navigation={{ current: null }} onJump={vi.fn()} />);
  expect(screen.getByRole("button", { name: "Step 1: Response, credit +0.35" }).lastElementChild).toHaveStyle({ height: "33px" });
  expect(screen.getByRole("button", { name: "Step 2: Response, credit +0.70, previous annotation" }).lastElementChild).toHaveStyle({ height: "40px" });
});

it("never replaces an explicit missing expected credit with a legacy categorical score", () => {
  const data = { ...response({ status: "completed", credits: [{ ...credit("0", 1), expected_credit: null }, { ...credit("1", 1), expected_credit: 0 }] } as TraceEvaluation), configured: true };
  const scores = automaticActionScores(data, steps);
  expect(scores.has("0")).toBe(false);
  expect(scores.get("1")?.credit).toBe(0);
  expect(automaticAnnotationProgress(data, steps, scores).unscoredReasons.get("0")).toBe("insufficient evidence");
});
