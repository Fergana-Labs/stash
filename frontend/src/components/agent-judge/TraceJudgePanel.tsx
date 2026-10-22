"use client";

import { useCallback, useEffect, useState } from "react";
import { Check, ChevronDown, ChevronRight, HelpCircle, Loader2, X } from "lucide-react";
import { errorMessage, relativeTime } from "@/components/reward-models/rm-text";
import { getJudgeReport, startInvestigation, traceJudgeReports, type Citation, type Claim, type ClaimStatus, type InvestigationReport, type JudgeReport } from "@/lib/agent-judge-api";
import { humanize } from "@/lib/behaviors-api";
import { cn } from "@/lib/utils";
import type { RmStep } from "@/lib/types";

const POLL_MS = 3000;
const VERDICT_STYLE = { supports: "text-emerald-700 dark:text-emerald-400", contradicts: "text-red-600 dark:text-red-400", insufficient: "text-muted-foreground" } as const;
const VERDICT_LABEL = { supports: "Supports", contradicts: "Contradicts", insufficient: "Not enough evidence" } as const;
const STATUS: Record<ClaimStatus, { icon: typeof Check; ring: string; label: string }> = {
  verified: { icon: Check, ring: "border-emerald-500 bg-emerald-500/12 text-emerald-700 dark:text-emerald-400", label: "Verified" },
  contradicted: { icon: X, ring: "border-red-500 bg-red-500/12 text-red-600 dark:text-red-400", label: "Contradicted" },
  unverifiable: { icon: HelpCircle, ring: "border-border bg-muted text-muted-foreground", label: "Unverifiable" },
};

type Jump = (index: number) => void;
type NumberOf = (index: number) => number;

/** Reports for a trace, polling running ones; starting a check adds one. */
export function useTraceJudge(traceId: string) {
  const [reports, setReports] = useState<JudgeReport[] | null>(null);
  const [starting, setStarting] = useState(false);
  const [error, setError] = useState("");
  const [latest, setLatest] = useState<string | null>(null);

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
        setReports((cur) => cur?.map((r) => { const f = fresh.find((x) => x.id === r.id); return f ? { ...r, ...f, model_name: r.model_name } : r; }) ?? cur);
      }).catch((e) => setError(errorMessage(e)));
    }, POLL_MS);
    return () => clearInterval(timer);
  }, [running]);

  async function check() {
    setStarting(true); setError("");
    try {
      const { id } = await startInvestigation(traceId);
      setLatest(id);
      await load();
      return id;
    } catch (e) {
      setError(errorMessage(e));
      return null;
    } finally {
      setStarting(false);
    }
  }
  return { reports, running: !!running, starting, error, check, latest };
}

/** "2 of 5 claims contradicted" / "All 5 claims verified": counts, not a probability. */
export function judgeHeadline(report: JudgeReport): { text: string; tone: "bad" | "good" | "neutral" } {
  if (report.status === "running") return { text: "Checking claims…", tone: "neutral" };
  if (report.status === "failed" || !report.report) return { text: "Claims check failed", tone: "neutral" };
  const claims = report.report.claims;
  const contradicted = claims.filter((c) => c.status === "contradicted").length;
  const verified = claims.filter((c) => c.status === "verified").length;
  if (!claims.length) return { text: "No checkable claims", tone: "neutral" };
  if (contradicted) return { text: `${contradicted} of ${claims.length} claim${claims.length === 1 ? "" : "s"} contradicted`, tone: "bad" };
  if (verified === claims.length) return { text: `All ${claims.length} claim${claims.length === 1 ? "" : "s"} verified`, tone: "good" };
  return { text: `${verified} of ${claims.length} claims verified · none contradicted`, tone: "neutral" };
}

export const headlineClass = (tone: "bad" | "good" | "neutral") => tone === "bad" ? "text-red-600 dark:text-red-400" : tone === "good" ? "text-emerald-700 dark:text-emerald-400" : "text-muted-foreground";

function StepLink({ index, numberOf, onJump, cited }: { index: number; numberOf: NumberOf; onJump: Jump; cited?: boolean }) {
  return <button type="button" onClick={() => onJump(index)} className={cn("shrink-0 font-mono text-[10.5px] hover:underline", cited ? "text-red-600 dark:text-red-400" : "text-brand-600")}>step {numberOf(index)}</button>;
}

/** Each quoted step once per report: the first (longest) quote stands for the step. */
export function evidenceByStep(r: InvestigationReport): Map<number, string> {
  const quotes = new Map<number, string>();
  for (const e of [...r.claims.flatMap((c) => c.evidence), ...r.findings.flatMap((f) => f.finding.evidence)]) {
    const current = quotes.get(e.idx);
    if (!current || e.quote.length > current.length) quotes.set(e.idx, e.quote);
  }
  return quotes;
}

/** The strongest evidence behind a claim: its first cited step, else an external fact. */
function strongest(c: Claim): { idx: number | null; text: string } | null {
  if (c.evidence.length) return { idx: c.evidence[0].idx, text: c.evidence[0].quote };
  if (c.external.length) return { idx: null, text: c.external[0] };
  return null;
}

/** Agent claims on top, the source of truth below, and the verdict between them. */
export function ClaimsGrid({ claims, quotes, numberOf, onJump }: { claims: Claim[]; quotes: Map<number, string>; numberOf: NumberOf; onJump: Jump }) {
  const shown = new Map<number, number>();
  return <div aria-label="Claims vs. source of truth" className="flex gap-2 overflow-x-auto pb-1">
    <div className="sticky left-0 z-10 grid w-16 shrink-0 grid-rows-[1fr_auto_1fr] gap-1.5 bg-background/95 text-[10px] font-medium text-muted-foreground">
      <span className="self-center">Agent claims</span><span className="h-6" /><span className="self-center">Evidence</span>
    </div>
    {claims.map((c, i) => {
      const s = STATUS[c.status];
      const Icon = s.icon;
      const ev = strongest(c);
      const repeatOf = ev?.idx != null ? shown.get(ev.idx) : undefined;
      if (ev?.idx != null && repeatOf === undefined) shown.set(ev.idx, i);
      return <div key={c.id} className={cn("grid w-56 shrink-0 grid-rows-[1fr_auto_1fr] gap-1.5", claims.length <= 4 && "flex-1")}>
        <div className="rounded border border-border bg-background px-2.5 py-1.5 text-[11.5px]">
          <p className="m-0 line-clamp-4">{c.text}</p>
          {c.step_idx != null && <StepLink index={c.step_idx} numberOf={numberOf} onJump={onJump} />}
        </div>
        <div className="flex justify-center"><span role="img" aria-label={s.label} title={s.label} className={cn("inline-flex size-6 items-center justify-center rounded-full border", s.ring)}><Icon className="size-3.5" /></span></div>
        <div className={cn("rounded border px-2.5 py-1.5 text-[11px]", c.status === "contradicted" ? "border-red-500/40" : c.status === "verified" ? "border-emerald-500/40" : " border-border")}>
          {!ev ? <span className="text-muted-foreground">No evidence found</span>
            : ev.idx === null ? <><span className="mr-1 text-[10px] text-muted-foreground">External</span>{ev.text}</>
            : repeatOf !== undefined ? <span className="text-muted-foreground">Same evidence as claim {repeatOf + 1} · <StepLink index={ev.idx} numberOf={numberOf} onJump={onJump} /></span>
            : <><p className="m-0 line-clamp-4 text-muted-foreground">“{quotes.get(ev.idx) ?? ev.text}”</p><StepLink index={ev.idx} numberOf={numberOf} onJump={onJump} /></>}
        </div>
      </div>;
    })}
  </div>;
}

const STEP_KIND: [RegExp, string][] = [[/^(read|view|cat|open)/i, "read"], [/(edit|write|patch|replace|create)/i, "edit"], [/(grep|glob|search|find|ls)/i, "search"], [/(bash|exec|shell|run|command)/i, "bash"]];
function chipOf(step: RmStep): string {
  if (step.role === "user") return "user";
  if (step.role === "system") return "system";
  if (step.tool_name) {
    const command = typeof step.tool_input?.command === "string" ? step.tool_input.command : "";
    if (/\b(test|pytest|vitest|jest)\b/.test(command)) return "test";
    return STEP_KIND.find(([re]) => re.test(step.tool_name!))?.[1] ?? step.tool_name.replace(/^mcp__/, "").split("__").at(-1)!.toLowerCase();
  }
  return "msg";
}

/** The whole trace as compact chips, cited steps in red; runs of identical uncited chips collapse ("read ×14"). */
export function JudgeReadStrip({ steps, cited, numberOf, onJump }: { steps: RmStep[]; cited: Set<number>; numberOf: NumberOf; onJump: Jump }) {
  // Tool results ride with their call.
  const shown = steps.filter((s) => s.role !== "tool" || cited.has(s.index));
  const runs: { kind: string; first: RmStep; count: number; cited: boolean }[] = [];
  for (const s of shown) {
    const kind = chipOf(s);
    const isCited = cited.has(s.index);
    const last = runs.at(-1);
    if (last && !isCited && !last.cited && last.kind === kind) last.count += 1;
    else runs.push({ kind, first: s, count: 1, cited: isCited });
  }
  return <div aria-label="What the judge read" className="flex flex-wrap gap-1">
    {runs.map((r) => <button key={r.first.id} type="button" onClick={() => onJump(r.first.index)} title={`step ${numberOf(r.first.index)}${r.count > 1 ? ` + ${r.count - 1} more` : ""}${r.cited ? " · cited" : ""}`}
      className={cn("rounded border px-1.5 py-px font-mono text-[10px]", r.cited ? "border-red-500 bg-red-500/12 text-red-600 dark:text-red-400" : "border-border text-muted-foreground hover:text-foreground")}>
      {r.kind}{r.count > 1 && ` ×${r.count}`}
    </button>)}
  </div>;
}

export function ReportBody({ report, steps, numberOf, onJump }: { report: JudgeReport; steps: RmStep[]; numberOf: NumberOf; onJump: Jump }) {
  const [whyOpen, setWhyOpen] = useState(false);
  const [investigationOpen, setInvestigationOpen] = useState(false);
  if (report.status === "running") return <p role="status" className="m-0 flex items-center gap-1.5 text-[11.5px] text-muted-foreground"><Loader2 className="size-3 animate-spin" />Investigating… workers are checking claims against the trajectory.</p>;
  if (report.status === "failed") return <p role="alert" className="m-0 text-[11.5px] text-destructive">{report.error || "The investigation failed."}</p>;
  const r = report.report;
  if (!r) return <p className="m-0 text-[11.5px] text-muted-foreground">No report was stored.</p>;
  const headline = judgeHeadline(report);
  const rationale = r.answers.supported?.rationale || Object.values(r.answers).map((a) => a.rationale).filter(Boolean).join("\n\n");
  const quotes = evidenceByStep(r);
  const cited = new Set(quotes.keys());
  const inGrid = new Set(r.claims.map((c) => c.evidence[0]?.idx).filter((i): i is number => i !== undefined));
  const citations = (evidence: Citation[]) => {
    const unique = [...new Set(evidence.map((e) => e.idx))];
    if (!unique.length) return null;
    return <ul className="m-0 mt-0.5 grid list-none gap-0.5 p-0">{unique.map((idx) => <li key={idx} className="flex gap-1.5 text-[11px] text-muted-foreground">
      <StepLink index={idx} numberOf={numberOf} onJump={onJump} cited />{!inGrid.has(idx) && <span className="min-w-0">“{quotes.get(idx)}”</span>}
    </li>)}</ul>;
  };
  return <div className="grid gap-2.5">
    <div className="text-[12px]">
      <p className="m-0"><b className={headlineClass(headline.tone)}>{headline.text}</b></p>
      {rationale && <><button type="button" aria-expanded={whyOpen} onClick={() => setWhyOpen(!whyOpen)} className="mt-0.5 inline-flex items-center gap-1 text-[11px] text-muted-foreground hover:text-foreground">{whyOpen ? <ChevronDown className="size-3" /> : <ChevronRight className="size-3" />}Why</button>
        {whyOpen && <p className="m-0 mt-0.5 whitespace-pre-wrap text-[11.5px] text-muted-foreground">{rationale}</p>}</>}
    </div>
    {r.claims.length > 0 && <ClaimsGrid claims={r.claims} quotes={quotes} numberOf={numberOf} onJump={onJump} />}
    <div>
      <button type="button" aria-expanded={investigationOpen} onClick={() => setInvestigationOpen(!investigationOpen)} className="inline-flex items-center gap-1 text-[11.5px] text-muted-foreground hover:text-foreground">
        {investigationOpen ? <ChevronDown className="size-3" /> : <ChevronRight className="size-3" />}Investigation · {r.findings.length} findings · {r.usage.workers} workers · {(r.usage.input_tokens + r.usage.output_tokens).toLocaleString()} tokens
      </button>
      {investigationOpen && <div className="mt-1.5 grid gap-1.5">
        {steps.length > 0 && <div className="rounded border border-border px-2.5 py-1.5"><p className="m-0 mb-1 text-[10.5px] text-muted-foreground">What the judge read · cited steps in red</p><JudgeReadStrip steps={steps} cited={cited} numberOf={numberOf} onJump={onJump} /></div>}
        <ul className="m-0 grid list-none gap-1.5 p-0">
          {r.findings.map((f, i) => <li key={i} className="rounded border border-border px-2.5 py-1.5 text-[11.5px]">
            <div className="flex flex-wrap items-center gap-1.5">
              <b className={VERDICT_STYLE[f.finding.verdict]}>{VERDICT_LABEL[f.finding.verdict] ?? humanize(f.finding.verdict)}</b>
              <span className="text-[10.5px] text-muted-foreground">{f.kind === "claim" ? "Claim check" : "Check"}</span>
              {f.finding.confidence != null && <span className="text-muted-foreground">{Math.round(f.finding.confidence * 100)}% confident</span>}
              {f.forked && <span className="rounded bg-brand-500/12 px-1 text-[10px] text-brand-600">Forked</span>}
            </div>
            <p className="m-0 mt-0.5 text-muted-foreground">{f.task}</p>
            {f.finding.summary && <p className="m-0 mt-0.5">{f.finding.summary}</p>}
            {citations(f.finding.evidence)}
          </li>)}
          <li className="text-[11px] text-muted-foreground">Usage: {r.usage.worker_calls} worker calls · {r.usage.input_tokens.toLocaleString()} in / {r.usage.output_tokens.toLocaleString()} out tokens · {r.usage.tool_calls.length} tool calls · {r.usage.forks} forks</li>
        </ul>
      </div>}
    </div>
  </div>;
}

/** Past claims checks on a trace, newest first, with a picker when there are several. */
export function JudgeReports({ reports, selected, onSelect, steps, numberOf, onJump }: {
  reports: JudgeReport[]; selected: string | null; onSelect: (id: string) => void; steps: RmStep[]; numberOf: NumberOf; onJump: Jump;
}) {
  const current = reports.find((r) => r.id === selected) ?? reports[0] ?? null;
  const label = (r: JudgeReport) => r.model_name ?? "Agent Judge";
  if (!current) return <p className="m-0 text-[11.5px] text-muted-foreground">No claims checks yet. Check claims to have the Agent Judge verify what the agent said it did against the trajectory.</p>;
  return <div className="grid gap-2.5">
    {reports.length > 1 ? <div className="flex flex-wrap gap-1">{reports.map((r) => <button key={r.id} type="button" aria-pressed={r.id === current.id} onClick={() => onSelect(r.id)}
      className={cn("rounded-md px-2 py-0.5 text-[11px]", r.id === current.id ? "bg-surface font-medium text-foreground" : "text-muted-foreground hover:text-foreground")}>
      {label(r)} · {relativeTime(r.created_at)}{r.status !== "done" && ` · ${humanize(r.status)}`}</button>)}</div>
      : <p className="m-0 text-[11px] text-muted-foreground">{label(current)} · {relativeTime(current.created_at)}</p>}
    <ReportBody key={current.id} report={current} steps={steps} numberOf={numberOf} onJump={onJump} />
  </div>;
}
