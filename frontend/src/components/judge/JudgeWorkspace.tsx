"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useMemo, useState } from "react";
import { Loader2, RefreshCw } from "lucide-react";
import { Button } from "@/components/ui/button";
import AutosaveTextarea from "@/components/evals/AutosaveTextarea";
import EvalAdvanced from "@/components/evals/EvalAdvanced";
import EvalEndpoint from "@/components/evals/EvalEndpoint";
import { evalSurfaceClass } from "@/components/evals/eval-ui";
import RefinePanel from "@/components/evals/RefinePanel";
import { errorMessage } from "@/components/reward-models/rm-text";
import { BRIEF_MARKER, imEditDraft, imGet, type JudgeProvider, type Item, type ModelDetail } from "@/lib/intuition-api";
import { Select } from "@/components/ui/select";
import { wzCreate, wzFromCorrections, wzReport, wzSessions, wzTrain, type TrainingReport } from "@/lib/wizard-api";
import { cn } from "@/lib/utils";
import { stageWizardMessage } from "@/components/wizard/wizard-navigation";
import { pct, WizardProvider, type WizardCtx } from "@/components/wizard/wizard-ui";
import BriefCard from "@/components/wizard/cards/BriefCard";
import CriteriaCard from "@/components/wizard/cards/CriteriaCard";
import PlaygroundCard from "@/components/wizard/cards/PlaygroundCard";
import type { Discovery } from "@/lib/wizard-api";
import ExamplesPanel from "./ExamplesPanel";
import HowItWorks from "./HowItWorks";
import InboxPanel from "./InboxPanel";
import ResultsPanel from "./ResultsPanel";
import EditViaMcp from "./EditViaMcp";
import UseIt from "./UseIt";

type Tab = "sandbox" | "setup" | "inbox" | "golden" | "results" | "how";
const TABS: { id: Tab; label: string; hint: string }[] = [
  { id: "setup", label: "Setup", hint: "What it decides and how" },
  { id: "sandbox", label: "Sandbox", hint: "Try an input and inspect its decision" },
  { id: "inbox", label: "Inbox", hint: "Review what it decided" },
  { id: "golden", label: "Golden set", hint: "The examples it learns from" },
  { id: "results", label: "Results", hint: "How well it agrees with you" },
  { id: "how", label: "How it works", hint: "How to build, use and connect an eval" },
];

/** The text the judge reads. Edits apply to the next version (Improve). */
function Instructions({ id, detail, onSaved }: { id: string; detail: ModelDetail; onSaved: () => void }) {
  const [current, fromBrief = ""] = ((detail.draft ?? detail.active)?.description ?? "").split(BRIEF_MARKER);

  return (
    <section aria-label="Instructions" className="rounded-lg border border-border p-3.5">
      <h3 className="m-0 mb-1.5 text-[13px] font-semibold">Instructions the judge reads</h3>
      <AutosaveTextarea key={id} value={current} label="Instructions the judge reads" rows={6} maxLength={6000} save={(description) => imEditDraft(id, { description })} onSaved={onSaved} />
      {fromBrief && <details className="mt-2 text-[11.5px] text-muted-foreground"><summary className="cursor-pointer">Also included automatically from the eval brief</summary><p className="whitespace-pre-wrap">{fromBrief}</p></details>}
      <p className="m-0 mt-1 text-[11px] text-muted-foreground">The judge reads these instructions together with the eval brief. Editing the brief updates that context automatically.</p>
    </section>
  );
}

const PROVIDERS: { value: JudgeProvider; label: string }[] = [
  { value: "jev", label: "Jev (single call)" },
  { value: "agent_judge", label: "Agent Judge (investigates traces)" },
];

/** Which judge answers the criteria. Switching clears the fitted head, so every example is graded again. */
function JudgeProviderPicker({ id, detail, onSaved }: { id: string; detail: ModelDetail; onSaved: () => void }) {
  const current = ((detail.draft ?? detail.active)?.provider ?? "jev") as JudgeProvider;
  const status = detail.judge.providers;
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  async function change(next: string) {
    if (next === current) return;
    if (status && !status[next as JudgeProvider]?.configured) { setError("That judge isn’t configured on this server."); return; }
    setBusy(true); setError("");
    try { await imEditDraft(id, { provider: next as JudgeProvider }); onSaved(); } catch (e) { setError(errorMessage(e)); } finally { setBusy(false); }
  }
  const options = PROVIDERS.map((p) => ({ ...p, label: status && !status[p.value]?.configured ? `${p.label} — not configured` : p.label }));
  const unavailable = status ? PROVIDERS.every((p) => p.value === current || !status[p.value]?.configured) : false;
  return (
    <section aria-label="Judge" className="rounded-lg border border-border p-3.5">
      <div className="mb-1.5 flex items-center justify-between gap-2">
        <h3 className="m-0 text-[13px] font-semibold">Judge</h3>
        <Select aria-label="Judge" value={current} onChange={(v) => void change(v)} options={options} disabled={busy || unavailable} className="h-7 w-64 text-xs" />
      </div>
      <p className="m-0 text-[11px] text-muted-foreground">
        {current === "agent_judge" ? "Investigates each trace with sub-agents, verifies claims step by step and keeps a report per verdict. Slower and costlier." : "Answers each criterion in one model call."}
        {" "}Switching judges re-grades every example and needs a retrain.
        {status?.[current]?.model && <span className="font-mono"> · {status[current].model}</span>}
      </p>
      {error && <p role="alert" className="m-0 mt-1 text-[11.5px] text-destructive">{error}</p>}
    </section>
  );
}

/**
 * One eval, one page: Setup (brief, instructions, criteria, try it, API),
 * Inbox (triage and expert review, by topic), Golden set (coverage, pins,
 * hygiene, labeling) and Results (training report, agreement). Wizard actions
 * resume unfinished setup; completed evals hand ongoing requests to MCP.
 */
export default function JudgeWorkspace({ id }: { id: string }) {
  const router = useRouter();
  const [detail, setDetail] = useState<ModelDetail | null>(null);
  const [report, setReport] = useState<TrainingReport | null>(null);
  const [tab, setTab] = useState<Tab>("setup");
  const [sandbox, setSandbox] = useState<{ item: Item; revision: number } | null>(null);
  const [version, setVersion] = useState(0);
  const [error, setError] = useState("");
  const [improving, setImproving] = useState(false);
  const [mcpRequest, setMcpRequest] = useState<{ id: number; text: string } | null>(null);
  const [openingWizard, setOpeningWizard] = useState(false);
  const [proposals, setProposals] = useState<{ key: number; items: Discovery["insights"] } | null>(null);

  const load = useCallback(async () => {
    try {
      const [d, r] = await Promise.all([imGet(id), wzReport(id)]);
      setDetail(d); setReport(r.report);
    } catch (e) { setError(errorMessage(e)); }
  }, [id]);
  useEffect(() => { void load(); }, [load, version]);
  const refresh = useCallback(() => setVersion((v) => v + 1), []);

  const openWizard = useCallback(async (message?: { text: string; kind: "message" | "event" }) => {
    if (detail?.active) {
      setMcpRequest({ id: Date.now(), text: message?.text ?? "Make the changes I request to this eval." });
      return;
    }
    setOpeningWizard(true); setError("");
    try {
      const existing = (await wzSessions()).sessions.find((s) => s.model_id === id);
      const sid = existing?.id ?? (await wzCreate(id)).id;
      if (message) stageWizardMessage(sid, { id: Date.now(), ...message });
      router.push(`/reward-models/wizard/${sid}`);
    } catch (e) { setError(errorMessage(e)); }
    finally { setOpeningWizard(false); }
  }, [id, router, detail?.active]);

  const ctx: WizardCtx = useMemo(() => ({
    modelId: id,
    refresh,
    version,
    busy: false,
    // Workspace edits refresh here; ongoing agent requests are handed off through MCP.
    send: (text, kind = "message") => {
      if (kind === "event") { refresh(); return; }
      void openWizard({ text, kind });
    },
  }), [id, refresh, version, openWizard]);

  async function improve() {
    setImproving(true); setError("");
    try { const r = await wzTrain(id); setReport(r); setTab("results"); refresh(); }
    catch (e) { setError(errorMessage(e)); } finally { setImproving(false); }
  }

  async function fromCorrections() {
    try { const found = await wzFromCorrections(id); setProposals({ key: Date.now(), items: found.insights }); }
    catch (e) { setError(errorMessage(e)); }
  }

  if (!detail) return <div className="p-5">{error ? <p role="alert" className="text-sm text-destructive">{error}</p> : <p role="status" className="text-xs text-muted-foreground">Loading eval…</p>}</div>;

  const counts = detail.counts;
  const inbox = (counts.inbox ?? 0) + (counts.escalated ?? 0);
  const live = detail.active;
  const fresh = counts.labeled === 0 && Object.keys(detail.model.brief ?? {}).length === 0;
  const headline = report?.holdout.accuracy != null
    ? `${pct(report.holdout.accuracy)} agreement with you on ${report.holdout.n} examples it didn't learn from`
    : live?.metrics?.eval.accuracy != null ? `${pct(live.metrics.eval.accuracy)} on ${live.metrics.eval.n} held-out` : "Not measured yet";

  return (
    <WizardProvider value={ctx}>
      <div className={cn(evalSurfaceClass, "flex h-full min-h-0 bg-background")}>
        <div className="scroll-thin min-w-0 flex-1 overflow-y-auto">
          <div className="mx-auto max-w-5xl px-5 pt-4 pb-8">
            <Link href="/reward-models/evals" className="text-xs text-muted-foreground hover:underline">Evals /</Link>
            <header className="mt-1 flex flex-wrap items-start justify-between gap-3">
              <div className="min-w-0">
                <h1 className="m-0 text-lg font-semibold tracking-tight">{detail.model.name}</h1>
                <p className="m-0 mt-0.5 text-[12.5px] text-muted-foreground">
                  <span className={cn("mr-1.5 inline-block size-1.5 rounded-full align-middle", live ? "bg-emerald-500" : "bg-muted-foreground/50")} />
                  {live ? `Live v${live.number}` : "Not live yet"} · {headline}
                </p>
              </div>
              <div className="flex items-center gap-2">
                <UseIt detail={detail} onShipped={refresh} />
                <Button size="sm" variant="outline" disabled={improving} onClick={() => void improve()} title="Retrain on every label and correction, and check it against the golden set. To rewrite the criteria themselves, use Improve rubric under Results.">
                  {improving ? <><Loader2 className="animate-spin" />Retraining…</> : <><RefreshCw />Retrain</>}
                </Button>
                {live ? <EditViaMcp id={id} name={detail.model.name} request={mcpRequest} /> : <Button size="sm" disabled={openingWizard} onClick={() => void openWizard()}>{openingWizard ? "Opening…" : "Resume setup"}</Button>}
              </div>
            </header>
            {error && <p role="alert" className="mt-2 text-xs text-destructive">{error}</p>}
            {fresh && (
              <div className="mt-4 flex flex-wrap items-center gap-3 rounded-lg border border-brand-500/30 bg-brand-500/5 px-4 py-3">
                <p className="m-0 flex-1 text-[13px]">New eval. The wizard asks a few questions, helps you label a handful of examples, and sets up criteria with you.</p>
                <Button size="sm" disabled={openingWizard} onClick={() => void openWizard({ text: "Help me set up this eval.", kind: "message" })}>Set it up with the wizard</Button>
              </div>
            )}

            <nav role="tablist" aria-label="Eval" className="scroll-thin mt-4 flex gap-1 border-b border-border max-sm:overflow-x-auto max-sm:overflow-y-hidden">
              {TABS.map((t) => (
                <button key={t.id} role="tab" type="button" aria-selected={tab === t.id} title={t.hint} onClick={() => setTab(t.id)} className={cn("-mb-px shrink-0 border-b-2 px-3 py-2 text-[13px] whitespace-nowrap", tab === t.id ? "border-foreground font-medium" : "border-transparent text-muted-foreground hover:text-foreground")}>
                  {t.label}
                  {t.id === "inbox" && inbox > 0 && <span className="ml-1.5 rounded-full bg-brand-500 px-1.5 py-px text-[10.5px] font-semibold text-white tabular-nums">{inbox}</span>}
                  {t.id === "golden" && <span className="ml-1.5 text-[11px] text-muted-foreground tabular-nums">{counts.labeled}</span>}
                </button>
              ))}
              <Link href={`/reward-models/evals/${id}/classic`} title="Production calls, monitoring and alerts, signals from other evals" className="ml-auto shrink-0 self-center px-2 text-[12px] whitespace-nowrap text-muted-foreground hover:text-foreground hover:underline">Monitoring &amp; usage →</Link>
            </nav>

            <div className="mt-4">
              {tab === "setup" && (
                <div className="grid items-start gap-4 lg:grid-cols-2">
                  <div className="min-w-0 flex flex-col gap-4 [&>section]:my-0">
                    <BriefCard />
                    <Instructions id={id} detail={detail} onSaved={refresh} />
                    <JudgeProviderPicker id={id} detail={detail} onSaved={refresh} />
                  </div>
                  <div className="min-w-0 flex flex-col gap-4 [&>section]:my-0">
                    <CriteriaCard key={proposals?.key ?? "criteria"} proposals={proposals?.items.map((i) => ({ ...i.question, insight: i.insight }))} />
                    <button type="button" onClick={() => void fromCorrections()} className="-mt-2 text-[11.5px] text-muted-foreground underline hover:text-foreground">Suggest criteria from reviewers’ corrections</button>
                    <PlaygroundCard />
                    <EvalEndpoint id={id} outputType={detail.model.output_type} />
                  </div>
                </div>
              )}
              {tab === "inbox" && <InboxPanel />}
              {tab === "golden" && <ExamplesPanel onTry={(item) => { setSandbox({ item, revision: Date.now() }); setTab("sandbox"); }} />}
              {tab === "sandbox" && <div className="max-w-3xl [&>section]:my-0"><PlaygroundCard key={sandbox?.revision ?? "empty"} item={sandbox?.item} editable title="Sandbox" /></div>}
              {tab === "results" && <div className="flex flex-col gap-4 [&>section]:my-0"><ResultsPanel /><EvalAdvanced version={detail.active ?? detail.draft} serving={!!detail.active} /><RefinePanel id={id} detail={detail} onChanged={refresh} /></div>}
              {tab === "how" && <HowItWorks id={id} name={detail.model.name} />}
            </div>
          </div>
        </div>
      </div>
    </WizardProvider>
  );
}
