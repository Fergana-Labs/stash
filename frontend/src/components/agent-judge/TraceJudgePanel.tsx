"use client";

import { useCallback, useEffect, useState } from "react";
import { ChevronDown, ChevronRight, Loader2, SearchCheck } from "lucide-react";
import { Button } from "@/components/ui/button";
import { errorMessage, relativeTime } from "@/components/reward-models/rm-text";
import { getJudgeReport, startInvestigation, traceJudgeReports, type Citation, type ClaimStatus, type JudgeReport } from "@/lib/agent-judge-api";
import { cn } from "@/lib/utils";

const POLL_MS = 3000;
const STATUS_STYLE: Record<ClaimStatus, string> = {
  verified: "bg-emerald-500/12 text-emerald-700 dark:text-emerald-400",
  contradicted: "bg-red-500/12 text-red-600 dark:text-red-400",
  unverifiable: "bg-muted text-muted-foreground",
};
const VERDICT_STYLE = { supports: "text-emerald-700 dark:text-emerald-400", contradicts: "text-red-600 dark:text-red-400", insufficient: "text-muted-foreground" } as const;

type Jump = (index: number) => void;

function StepLink({ index, numberOf, onJump }: { index: number; numberOf: (index: number) => number; onJump: Jump }) {
  return <button type="button" onClick={() => onJump(index)} className="shrink-0 font-mono text-[10.5px] text-brand-600 hover:underline">step {numberOf(index)}</button>;
}

function Citations({ evidence, numberOf, onJump }: { evidence: Citation[]; numberOf: (index: number) => number; onJump: Jump }) {
  if (!evidence.length) return null;
  return <ul className="m-0 grid list-none gap-0.5 p-0">{evidence.map((e, i) => <li key={i} className="flex gap-1.5 text-[11px] text-muted-foreground"><StepLink index={e.idx} numberOf={numberOf} onJump={onJump} /><span className="min-w-0">“{e.quote}”</span></li>)}</ul>;
}

function ReportBody({ report, numberOf, onJump }: { report: JudgeReport; numberOf: (index: number) => number; onJump: Jump }) {
  const [investigationOpen, setInvestigationOpen] = useState(false);
  if (report.status === "running") return <p role="status" className="m-0 flex items-center gap-1.5 text-[11.5px] text-muted-foreground"><Loader2 className="size-3 animate-spin" />Investigating… workers are checking claims against the trajectory.</p>;
  if (report.status === "failed") return <p role="alert" className="m-0 text-[11.5px] text-destructive">{report.error || "The investigation failed."}</p>;
  const r = report.report;
  if (!r) return <p className="m-0 text-[11.5px] text-muted-foreground">No report was stored.</p>;
  const supported = r.answers.supported;
  const unsupported = supported?.probabilities.false;
  const counts = { verified: 0, contradicted: 0, unverifiable: 0 };
  for (const c of r.claims) counts[c.status] += 1;
  return <div className="grid gap-2.5">
    <div className="text-[12px]">
      {unsupported != null
        ? <p className="m-0"><b className={unsupported >= 0.5 ? "text-red-600 dark:text-red-400" : "text-emerald-700 dark:text-emerald-400"}>{unsupported >= 0.5 ? "Likely unsupported claims" : "Claims look supported"}</b> <span className="text-muted-foreground">· P(unsupported) {Math.round(unsupported * 100)}%</span></p>
        : Object.entries(r.answers).map(([qid, a]) => <p key={qid} className="m-0"><span className="font-mono text-[11px] text-muted-foreground">{qid}</span> {Object.entries(a.probabilities).map(([o, p]) => `${o} ${Math.round(p * 100)}%`).join(" · ")}</p>)}
      {supported?.rationale && <p className="m-0 mt-0.5 text-[11.5px] text-muted-foreground">{supported.rationale}</p>}
      <p className="m-0 mt-0.5 text-[11px] text-muted-foreground">{r.claims.length} claims · {counts.verified} verified · {counts.contradicted} contradicted · {counts.unverifiable} unverifiable</p>
    </div>
    {r.claims.length > 0 && <ul aria-label="Claims ledger" className="m-0 grid list-none divide-y divide-border rounded border border-border p-0">
      {r.claims.map((c) => <li key={c.id} className="grid gap-1 px-2.5 py-1.5">
        <div className="flex items-start gap-2 text-[12px]">
          <span className={cn("shrink-0 rounded px-1.5 py-px text-[10.5px] font-medium", STATUS_STYLE[c.status])}>{c.status}</span>
          <span className="min-w-0 flex-1">{c.text}</span>
          {c.step_idx != null && <StepLink index={c.step_idx} numberOf={numberOf} onJump={onJump} />}
        </div>
        <Citations evidence={c.evidence} numberOf={numberOf} onJump={onJump} />
        {c.external.length > 0 && <ul className="m-0 list-none p-0 text-[11px] text-muted-foreground">{c.external.map((x, i) => <li key={i}><span className="mr-1 text-[10px] uppercase">external</span>{x}</li>)}</ul>}
      </li>)}
    </ul>}
    <div>
      <button type="button" aria-expanded={investigationOpen} onClick={() => setInvestigationOpen(!investigationOpen)} className="inline-flex items-center gap-1 text-[11.5px] text-muted-foreground hover:text-foreground">
        {investigationOpen ? <ChevronDown className="size-3" /> : <ChevronRight className="size-3" />}Investigation · {r.findings.length} findings · {r.usage.workers} workers · {r.usage.forks} forks · {(r.usage.input_tokens + r.usage.output_tokens).toLocaleString()} tokens
      </button>
      {investigationOpen && <ul className="m-0 mt-1.5 grid list-none gap-1.5 p-0">
        {r.findings.map((f, i) => <li key={i} className="rounded border border-border px-2.5 py-1.5 text-[11.5px]">
          <div className="flex flex-wrap items-center gap-1.5">
            <span className="font-mono text-[10.5px] text-muted-foreground">{f.kind}:{f.ref}</span>
            <b className={VERDICT_STYLE[f.finding.verdict]}>{f.finding.verdict}</b>
            {f.finding.confidence != null && <span className="text-muted-foreground">{Math.round(f.finding.confidence * 100)}%</span>}
            {f.forked && <span className="rounded bg-brand-500/12 px-1 text-[10px] text-brand-600">forked</span>}
          </div>
          <p className="m-0 mt-0.5 text-muted-foreground">{f.task}</p>
          {f.finding.summary && <p className="m-0 mt-0.5">{f.finding.summary}</p>}
          <Citations evidence={f.finding.evidence} numberOf={numberOf} onJump={onJump} />
        </li>)}
        <li className="text-[11px] text-muted-foreground">Usage: {r.usage.worker_calls} worker calls · {r.usage.input_tokens.toLocaleString()} in / {r.usage.output_tokens.toLocaleString()} out tokens · {r.usage.tool_calls.length} tool calls · budget {r.budget.claims} claims, {r.budget.forks} forks, {r.budget.worker_turns} worker turns</li>
      </ul>}
    </div>
  </div>;
}

/** Agent Judge on this trace: start a claims check and read past investigations. Collapsed by default. */
export default function TraceJudgePanel({ traceId, numberOf, onJump }: { traceId: string; numberOf: (index: number) => number; onJump: Jump }) {
  const [open, setOpen] = useState(false);
  const [reports, setReports] = useState<JudgeReport[] | null>(null);
  const [selected, setSelected] = useState<string | null>(null);
  const [starting, setStarting] = useState(false);
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    try { setReports((await traceJudgeReports(traceId)).reports); }
    catch { setReports([]); /* Optional panel: an unavailable judge leaves the trace usable. */ }
  }, [traceId]);
  useEffect(() => { void load(); }, [load]);

  const running = reports?.filter((r) => r.status === "running").map((r) => r.id).join(",") ?? "";
  useEffect(() => {
    if (!running) return;
    const timer = setInterval(() => {
      void Promise.all(running.split(",").map((id) => getJudgeReport(id))).then((fresh) => {
        setReports((cur) => cur?.map((r) => fresh.find((f) => f.id === r.id) ? { ...r, ...fresh.find((f) => f.id === r.id)!, model_name: r.model_name } : r) ?? cur);
      }).catch((e) => setError(errorMessage(e)));
    }, POLL_MS);
    return () => clearInterval(timer);
  }, [running]);

  async function check() {
    setStarting(true); setError("");
    try {
      const { id } = await startInvestigation(traceId);
      setOpen(true);
      setSelected(id);
      await load();
    } catch (e) {
      setError(errorMessage(e));
    } finally {
      setStarting(false);
    }
  }

  const current = reports?.find((r) => r.id === selected) ?? reports?.[0] ?? null;
  const label = (r: JudgeReport) => r.model_name ?? "Unsupported-claims check";
  return <section aria-label="Agent Judge" className="text-[12px]">
    <div className="flex items-center gap-2">
      <button type="button" aria-expanded={open} onClick={() => setOpen(!open)} className="inline-flex items-center gap-1 text-[11px] text-muted-foreground hover:text-foreground">
        {open ? <ChevronDown className="size-3" /> : <ChevronRight className="size-3" />}Judge{reports?.length ? ` · ${reports.length} report${reports.length === 1 ? "" : "s"}` : ""}
        {running && <Loader2 className="ml-1 size-3 animate-spin" />}
      </button>
      <Button size="xs" variant="outline" disabled={starting || !!running} onClick={() => void check()}><SearchCheck />{starting ? "Starting…" : running ? "Checking…" : "Check claims"}</Button>
      {error && <span role="alert" className="text-[11px] text-destructive">{error}</span>}
    </div>
    {open && <div className="scroll-thin mt-2 max-h-[40vh] overflow-y-auto rounded-md border border-border bg-surface/30 p-2.5">
      {!reports ? <p role="status" className="m-0 text-[11.5px] text-muted-foreground">Loading reports…</p>
        : !reports.length ? <p className="m-0 text-[11.5px] text-muted-foreground">No investigations yet. Check claims to have the Agent Judge verify what the agent said it did against the trajectory.</p>
        : <div className="grid gap-2.5">
          {reports.length > 1 && <div className="flex flex-wrap gap-1">{reports.map((r) => <button key={r.id} type="button" aria-pressed={r.id === current?.id} onClick={() => setSelected(r.id)}
            className={cn("rounded-md px-2 py-0.5 text-[11px]", r.id === current?.id ? "bg-surface font-medium text-foreground" : "text-muted-foreground hover:text-foreground")}>
            {label(r)} · {relativeTime(r.created_at)}{r.status !== "done" && ` · ${r.status}`}</button>)}</div>}
          {current && <>
            {reports.length === 1 && <p className="m-0 text-[11px] text-muted-foreground">{label(current)} · {relativeTime(current.created_at)}</p>}
            <ReportBody key={current.id} report={current} numberOf={numberOf} onJump={onJump} />
          </>}
        </div>}
    </div>}
  </section>;
}
