import { fireEvent, render, screen, within } from "@testing-library/react";
import { beforeEach, expect, it, vi } from "vitest";
import RunClient from "./RunClient";
import type { ResultRow, RunDetail } from "@/lib/test-sets-api";

const api = vi.hoisted(() => ({ getRun: vi.fn(), get: vi.fn() }));
vi.mock("@/components/BreadcrumbContext", () => ({ useBreadcrumbs: () => {} }));
vi.mock("@/lib/test-sets-api", async (importOriginal) => ({ ...(await importOriginal<object>()), tsGetRun: api.getRun, tsGet: api.get }));

const result = (name: string, passed: boolean, baseline_passed: boolean | null, reason = ""): ResultRow => ({
  case_id: name, case_name: name, input: `${name}?`, expected: "right", output: "answer", trace_id: null,
  scores: [{ scorer: "expected", passed, reason }], passed, error: null, baseline_passed, baseline_output: baseline_passed === null ? null : "old answer",
});

beforeEach(() => {
  vi.clearAllMocks();
  api.get.mockResolvedValue({ name: "Support regressions" });
  api.getRun.mockResolvedValue({
    id: "r2", set_id: "s1", label: "v2", status: "done", error: null, baseline_run_id: "r1", created_at: "", finished_at: "",
    summary: { cases: 3, passed: 2, pass_rate: 2 / 3, errors: 0, scorers: {}, baseline: { pass_rate: 1, cases: 3 }, broke: ["refund"], fixed: [], gate: "fail" },
    results: [result("warranty", true, true), result("refund", false, true, "Contradicts the 30-day policy"), result("status", true, true)],
  } satisfies RunDetail);
});

it("summarizes the run, lists what broke first, and filters by status", async () => {
  render(<RunClient runId="r2" />);
  expect(await screen.findByText("2/3")).toBeInTheDocument();
  expect(screen.getByText("baseline 100%")).toBeInTheDocument();
  expect(screen.getByText("Fail")).toBeInTheDocument();
  const rows = within(screen.getByRole("table", { name: "Results" })).getAllByRole("row").slice(1);
  expect(rows[0]).toHaveTextContent("refund");
  expect(rows[0]).toHaveTextContent("Broke");
  expect(rows[0]).toHaveTextContent("Contradicts the 30-day policy");

  fireEvent.click(screen.getByRole("button", { name: /^Broke/ }));
  expect(within(screen.getByRole("table", { name: "Results" })).getAllByRole("row")).toHaveLength(2);

  fireEvent.click(screen.getByRole("button", { name: "Expand refund" }));
  expect(screen.getByText("Baseline (passed)")).toBeInTheDocument();
  expect(screen.getByText("old answer")).toBeInTheDocument();
});

it("marks a case that couldn't be scored apart from a failure and links the baseline run", async () => {
  api.getRun.mockResolvedValueOnce({
    id: "r3", set_id: "s1", label: "v3", status: "done", error: null, baseline_run_id: "r1", created_at: "", finished_at: "",
    summary: { cases: 1, passed: 0, pass_rate: 0, errors: 1, scorers: {}, baseline: { pass_rate: 1, cases: 1 }, broke: [], fixed: [], gate: "pass" },
    results: [{ ...result("refund", false, true), scores: [], error: "Scoring failed: Jev request failed (HTTP 402)" }],
  } satisfies RunDetail);
  render(<RunClient runId="r3" />);
  expect(await screen.findByText("Not scored")).toBeInTheDocument();
  expect(within(screen.getByRole("table", { name: "Results" })).queryByText("Broke")).toBeNull();
  expect(screen.getByText("Scoring failed: Jev request failed (HTTP 402)")).toBeInTheDocument();
  expect(screen.getByRole("link", { name: "baseline 100%" })).toHaveAttribute("href", "/reward-models/evals/test-sets/runs/r1");
});
