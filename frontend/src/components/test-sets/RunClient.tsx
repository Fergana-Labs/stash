"use client";

import Link from "next/link";
import { Fragment, useCallback, useEffect, useState } from "react";
import { ChevronDown, ChevronRight } from "lucide-react";
import { toast } from "sonner";
import { useBreadcrumbs } from "@/components/BreadcrumbContext";
import { EvalPageFrame } from "@/components/evals/eval-ui";
import { errorMessage } from "@/components/reward-models/rm-text";
import { GateBadge, notFoundMessage } from "@/components/test-sets/test-set-ui";
import { pct, runHref, setHref, tsGet, tsGetRun, type CaseInput, type ResultRow, type RunDetail } from "@/lib/test-sets-api";
import { cn } from "@/lib/utils";

const POLL_MS = 3000;

export type ResultStatus = "broke" | "fixed" | "pass" | "fail" | "error";
export function resultStatus(r: ResultRow): ResultStatus {
  if (r.error) return "error";
  if (r.passed && r.baseline_passed === false) return "fixed";
  if (!r.passed && r.baseline_passed === true) return "broke";
  return r.passed ? "pass" : "fail";
}
const ORDER: Record<ResultStatus, number> = { broke: 0, fail: 1, error: 2, fixed: 3, pass: 4 };
const FILTERS = [
  { value: "all", label: "All" }, { value: "broke", label: "Broke" }, { value: "fixed", label: "Fixed" }, { value: "failing", label: "Failing" },
] as const;
type Filter = (typeof FILTERS)[number]["value"];

/** Results in reading order: what broke first, then the rest of the failures, then passes. */
export function sortResults(results: ResultRow[]) {
  return [...results].sort((a, b) => ORDER[resultStatus(a)] - ORDER[resultStatus(b)]);
}

function matches(filter: Filter, r: ResultRow) {
  const s = resultStatus(r);
  return filter === "all" || (filter === "failing" ? !r.passed : s === filter);
}

export function RunSummaryLine({ run }: { run: RunDetail }) {
  const s = run.summary;
  if (run.status === "scoring") return <p className="text-xs text-muted-foreground" role="status">Scoring {run.results.length} answers…</p>;
  if (run.status === "failed" || !s) return <p className="text-xs text-destructive">{run.error ?? "Scoring failed"}</p>;
  return <p className="flex flex-wrap items-center gap-x-2 text-[13px]">
    <span><span className="font-medium tabular-nums">{s.passed}/{s.cases}</span> passed ({pct(s.pass_rate)})</span>
    {s.baseline && <><span className="text-muted-foreground">·</span>{run.baseline_run_id
      ? <Link href={runHref(run.baseline_run_id)} className="text-muted-foreground hover:text-foreground hover:underline" title="Open the run this one is compared with">baseline {pct(s.baseline.pass_rate)}</Link>
      : <span className="text-muted-foreground">baseline {pct(s.baseline.pass_rate)}</span>}
      <span className="text-muted-foreground">·</span><span className="inline-flex items-center gap-1.5">Gate: <GateBadge gate={s.gate} /></span></>}
    {s.errors > 0 && <><span className="text-muted-foreground">·</span><span className="text-destructive">{s.errors} couldn’t be scored</span></>}
  </p>;
}

export default function RunClient({ runId }: { runId: string }) {
  const [run, setRun] = useState<RunDetail | null>(null);
  const [setName, setSetName] = useState("");
  const [error, setError] = useState("");
  const [filter, setFilter] = useState<Filter>("all");
  const [open, setOpen] = useState<Set<string>>(new Set());
  useBreadcrumbs([
    { label: "Evals", href: "/reward-models/evals" }, { label: "Test sets", href: "/reward-models/evals/test-sets" },
    ...(run ? [{ label: setName || "Test set", href: setHref(run.set_id) }] : []), { label: run?.label || "Run" },
  ], `test-run:${runId}:${setName}:${run?.label ?? ""}`);

  const load = useCallback(async () => { try { setRun(await tsGetRun(runId)); setError(""); } catch (e) { setError(notFoundMessage(e, "This run doesn’t exist or isn’t yours.")); } }, [runId]);
  useEffect(() => { void load(); }, [load]);
  const setId = run?.set_id;
  useEffect(() => { if (setId) tsGet(setId).then((s) => setSetName(s.name)).catch((e) => toast.error(errorMessage(e))); }, [setId]);
  const scoring = run?.status === "scoring";
  useEffect(() => {
    if (!scoring) return;
    const timer = setInterval(() => void load(), POLL_MS);
    return () => clearInterval(timer);
  }, [scoring, load]);

  if (!run) return <EvalPageFrame>{error ? <p role="alert" className="text-xs text-destructive">{error}</p> : <p role="status" className="text-xs text-muted-foreground">Loading run…</p>}</EvalPageFrame>;

  const rows = sortResults(run.results);
  const shown = rows.filter((r) => matches(filter, r));
  const toggle = (id: string) => setOpen((cur) => { const next = new Set(cur); if (next.has(id)) next.delete(id); else next.add(id); return next; });

  return <EvalPageFrame title={run.label || "Unlabeled run"}
    actions={<Link href={setHref(run.set_id)} className="shrink-0 text-xs text-muted-foreground hover:text-foreground hover:underline">← {setName || "Test set"}</Link>}>
    <div className="-mt-3 mb-5"><RunSummaryLine run={run} /></div>
    <nav aria-label="Filter results" className="mb-3 flex gap-1 text-xs">{FILTERS.map((f) => {
      const n = rows.filter((r) => matches(f.value, r)).length;
      return <button key={f.value} type="button" aria-pressed={filter === f.value} onClick={() => setFilter(f.value)}
        className={cn("rounded-md px-2 py-1", filter === f.value ? "bg-surface font-medium text-foreground" : "text-muted-foreground hover:text-foreground")}>
        {f.label} <span className="tabular-nums text-muted-foreground">{n}</span></button>;
    })}</nav>
    <div className="overflow-x-auto rounded border border-border"><table aria-label="Results" className="w-full min-w-[720px] table-fixed text-left text-xs">
      <thead className="border-b border-border bg-surface/60 text-muted-foreground"><tr className="h-8 [&>th]:px-3 [&>th]:font-medium"><th className="w-8" /><th className="w-56">Case</th><th className="w-20">Result</th><th>Why</th></tr></thead>
      <tbody>
        {shown.map((r) => {
          const status = resultStatus(r);
          const expanded = open.has(r.case_id);
          const why = r.error ?? r.scores.filter((s) => !s.passed).map((s) => s.reason).join(" · ");
          return <Fragment key={r.case_id}>
            <tr className="cursor-pointer border-b border-border align-top hover:bg-surface/60 [&>td]:px-3 [&>td]:py-2" onClick={() => toggle(r.case_id)}>
              <td><button type="button" aria-expanded={expanded} aria-label={`${expanded ? "Collapse" : "Expand"} ${r.case_name || "case"}`} className="text-muted-foreground">{expanded ? <ChevronDown className="size-3.5" /> : <ChevronRight className="size-3.5" />}</button></td>
              <td className="truncate font-medium" title={r.case_name}>{r.case_name || "Untitled"}</td>
              <td><StatusBadge status={status} /></td>
              <td className={cn("text-muted-foreground", !expanded && "line-clamp-2")}>{why || (r.passed ? "" : "—")}</td>
            </tr>
            {expanded && <tr className="border-b border-border bg-surface/30"><td colSpan={4} className="px-3 py-3"><ResultDetail r={r} /></td></tr>}
          </Fragment>;
        })}
        {!shown.length && <tr><td colSpan={4} className="px-3 py-8 text-muted-foreground">{run.results.length ? "Nothing here." : "This run has no results."}</td></tr>}
      </tbody>
    </table></div>
  </EvalPageFrame>;
}

export function StatusBadge({ status }: { status: ResultStatus }) {
  const style = { broke: "bg-destructive/10 text-destructive", fail: "text-destructive", error: "text-muted-foreground", fixed: "bg-success/10 text-success", pass: "text-success" }[status];
  const label = { broke: "Broke", fail: "Fail", error: "Not scored", fixed: "Fixed", pass: "Pass" }[status];
  return <span className={cn("inline-flex whitespace-nowrap rounded px-1.5 py-0.5 text-[11px] font-medium", style)}>{label}</span>;
}

function inputText(input: CaseInput) {
  return typeof input === "string" ? input : input.map((t) => `${t.role === "user" ? "User" : t.role === "assistant" ? "Agent" : t.role}: ${t.content}`).join("\n\n");
}

function Block({ label, text, muted }: { label: string; text: string | null; muted?: boolean }) {
  return <div className="min-w-0"><div className="mb-1 text-[11px] font-medium text-muted-foreground">{label}</div>
    <div className={cn("max-h-64 overflow-y-auto whitespace-pre-wrap rounded border border-border bg-background px-2.5 py-2 leading-5", muted && "text-muted-foreground")}>{text || "—"}</div></div>;
}

function ResultDetail({ r }: { r: ResultRow }) {
  return <div className="grid gap-3">
    <Block label="Input" text={inputText(r.input)} />
    <div className={cn("grid gap-3", r.baseline_output !== null ? "md:grid-cols-3" : "md:grid-cols-2")}>
      <Block label="Expected" text={r.expected} />
      <Block label="This run" text={r.output} />
      {r.baseline_output !== null && <Block label={`Baseline (${r.baseline_passed ? "passed" : "failed"})`} text={r.baseline_output} muted />}
    </div>
    {(r.passed || r.scores.length > 1) && r.scores.length > 0 && <ul className="grid gap-1">{r.scores.map((s, i) => <li key={i}><span className={s.passed ? "text-success" : "text-destructive"}>{s.passed ? "Pass" : "Fail"}</span> · {s.scorer === "expected" ? "Expected answer" : `Eval${s.label ? ` (${s.label})` : ""}`}: <span className="text-muted-foreground">{s.reason}</span></li>)}</ul>}
    {r.trace_id && <Link href={`/reward-models/traces/${r.trace_id}`} className="text-muted-foreground underline hover:text-foreground">Open trace</Link>}
  </div>;
}
