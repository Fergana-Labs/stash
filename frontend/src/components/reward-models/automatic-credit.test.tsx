import { render, screen } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import type { RmStep } from "@/lib/types";
import type { TraceEvaluation, TraceEvaluationResponse } from "@/lib/workbench-api";
import { automaticActionScores } from "./automatic-credit";
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
  expect(screen.getByRole("button", { name: "Step 3: Response, unscored" }).lastElementChild).toHaveStyle({ height: "6px" });
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
