import { apiFetch } from "@/lib/api";

/** Client for /api/v1/test-sets (backend/routers/test_sets.py): regression tests for agents. */
const TS = "/api/v1/test-sets";

export type Scorer = { type: "expected" } | { type: "eval"; eval_id: string; pass_labels: string[] };
export interface Turn { role: string; content: string }
export type CaseInput = string | Turn[];

export interface RunSummary {
  cases: number;
  passed: number;
  pass_rate: number | null;
  errors: number;
  /** "expected" or "eval:<id>" → pass rate. */
  scorers: Record<string, number>;
  baseline: { pass_rate: number | null; cases: number } | null;
  broke: string[];
  fixed: string[];
  gate: "pass" | "fail";
}

export type RunStatus = "scoring" | "done" | "failed";
export interface RunRow {
  id: string; label: string; status: RunStatus; error: string | null; baseline_run_id: string | null;
  summary: RunSummary | null; created_at: string; finished_at: string | null;
}

export interface TestCase {
  id: string; name: string; input: CaseInput; expected: string | null; source_trace_id: string | null; created_at: string;
}

export interface TestSetSummary {
  id: string; name: string; description: string; scorers: Scorer[]; max_regressions: number;
  baseline_run_id: string | null; case_count: number; created_at: string; updated_at: string;
  last_run: Pick<RunRow, "id" | "label" | "status" | "summary" | "created_at"> | null;
}

export interface TestSet extends Omit<TestSetSummary, "case_count" | "last_run"> {
  cases: TestCase[];
  runs: RunRow[];
}

export interface ScoreRow { scorer: "expected" | "eval"; passed: boolean; reason: string; label?: string; eval_id?: string }
export interface ResultRow {
  case_id: string; case_name: string; input: CaseInput; expected: string | null; output: string; trace_id: string | null;
  scores: ScoreRow[]; passed: boolean | null; error: string | null; baseline_passed: boolean | null; baseline_output: string | null;
}
export interface RunDetail extends RunRow { set_id: string; results: ResultRow[] }

export interface NewCase { name?: string; input: CaseInput; expected?: string | null }

const send = <T>(path: string, method: string, body?: unknown) =>
  apiFetch<T>(path, { method, body: body === undefined ? undefined : JSON.stringify(body) });

export const tsList = () => apiFetch<{ test_sets: TestSetSummary[] }>(TS);
export const tsCreate = (body: { name: string; description?: string; scorers?: Scorer[]; max_regressions?: number }) =>
  send<TestSetSummary>(TS, "POST", body);
export const tsGet = (id: string) => apiFetch<TestSet>(`${TS}/${id}`);
export const tsUpdate = (id: string, body: { name?: string; description?: string; scorers?: Scorer[]; max_regressions?: number; baseline_run_id?: string | null }) =>
  send<TestSet>(`${TS}/${id}`, "PATCH", body);
export const tsDelete = (id: string) => send<void>(`${TS}/${id}`, "DELETE");
export const tsAddCases = (id: string, cases: NewCase[]) => send<{ cases: TestCase[] }>(`${TS}/${id}/cases`, "POST", { cases });
export const tsCaseFromTrace = (id: string, body: { trace_id: string; upto_idx?: number; expected?: string | null }) =>
  send<TestCase>(`${TS}/${id}/cases/from-trace`, "POST", body);
export const tsUpdateCase = (id: string, caseId: string, body: Partial<NewCase>) => send<TestCase>(`${TS}/${id}/cases/${caseId}`, "PATCH", body);
export const tsDeleteCase = (id: string, caseId: string) => send<void>(`${TS}/${id}/cases/${caseId}`, "DELETE");
export const tsGetRun = (runId: string) => apiFetch<RunDetail>(`${TS}/runs/${runId}`);

export const setHref = (id: string) => `/reward-models/evals/test-sets/${id}`;
export const runHref = (runId: string) => `/reward-models/evals/test-sets/runs/${runId}`;

export const pct = (rate: number | null | undefined) => rate == null ? "—" : `${Math.round(rate * 100)}%`;

/** One line for a case input: the last user message, plus how many earlier turns it carries. */
export function inputPreview(input: CaseInput): { text: string; earlier: number } {
  if (typeof input === "string") return { text: input, earlier: 0 };
  const last = input.map((t, i) => [t, i] as const).filter(([t]) => t.role === "user").at(-1);
  if (!last) return { text: input.at(-1)?.content ?? "", earlier: Math.max(0, input.length - 1) };
  return { text: last[0].content, earlier: last[1] };
}

/** Cases from a JSONL file: one {name?, input, expected?} per line; blank lines skipped. */
export function parseCasesJsonl(text: string): NewCase[] {
  return text.split("\n").map((line, i) => [line.trim(), i + 1] as const).filter(([line]) => line).map(([line, n]) => {
    let row: unknown;
    try { row = JSON.parse(line); } catch { throw new Error(`Line ${n} is not valid JSON`); }
    if (!row || typeof row !== "object" || !("input" in row)) throw new Error(`Line ${n} needs an "input"`);
    const r = row as Record<string, unknown>;
    if (typeof r.input !== "string" && !Array.isArray(r.input)) throw new Error(`Line ${n}: "input" must be text or a list of {role, content}`);
    return {
      name: typeof r.name === "string" ? r.name : undefined,
      input: r.input as CaseInput,
      expected: typeof r.expected === "string" ? r.expected : null,
    };
  });
}

/** How a run row reads: newest-first runs compared against the baseline they ran with. */
export function runDelta(summary: RunSummary | null): number | null {
  if (!summary?.baseline || summary.pass_rate == null || summary.baseline.pass_rate == null) return null;
  return summary.pass_rate - summary.baseline.pass_rate;
}

/** The run the next one compares against: the pinned baseline, else the latest finished run. */
export function effectiveBaseline(set: Pick<TestSet, "baseline_run_id" | "runs">): string | null {
  // Mirrors the backend: the pinned run, else the latest run that passed its gate.
  return set.baseline_run_id ?? set.runs.find((r) => r.status === "done" && r.summary?.gate === "pass")?.id ?? null;
}
