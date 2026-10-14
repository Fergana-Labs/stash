"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Wand2 } from "lucide-react";
import { ResizableHandle, ResizablePanel, ResizablePanelGroup } from "@/components/ui/resizable";
import { errorMessage } from "@/components/reward-models/rm-text";
import { imGet, type ModelDetail } from "@/lib/intuition-api";
import { wzCreate, wzGet, wzReport, wzSessions, type TrainingReport } from "@/lib/wizard-api";
import { cn } from "@/lib/utils";
import WizardChat, { type Injected } from "@/components/wizard/WizardChat";
import { pct, WizardProvider, type WizardCtx } from "@/components/wizard/wizard-ui";
import PlaygroundCard from "@/components/wizard/cards/PlaygroundCard";
import EvalEndpoint from "@/components/evals/EvalEndpoint";
import ExamplesPanel from "./ExamplesPanel";
import HowItWorks from "./HowItWorks";
import InboxPanel from "./InboxPanel";
import ResultsPanel from "./ResultsPanel";
import SetupPanel from "./SetupPanel";
import UseIt from "./UseIt";

type Tab = "setup" | "golden" | "inbox" | "try" | "results" | "how";
const TABS: { id: Tab; label: string }[] = [
  { id: "how", label: "How it works" },
  { id: "setup", label: "Setup" },
  { id: "golden", label: "Golden set" },
  { id: "inbox", label: "Inbox" },
  { id: "try", label: "Try it" },
  { id: "results", label: "Results" },
];

function Placeholder() {
  return (
    <div className="grid h-full place-items-center p-8 text-center">
      <div className="max-w-sm">
        <div className="mx-auto mb-3 grid size-10 place-items-center rounded-xl bg-brand-500/10 text-brand-600 dark:text-brand-400"><Wand2 className="size-5" /></div>
        <h2 className="m-0 text-[15px] font-semibold">Your intuition appears here</h2>
        <p className="m-0 mt-1 text-[12.5px] text-muted-foreground">Tell the wizard what judgment call it should make. As you answer, the brief, examples, criteria and results fill in on this side.</p>
      </div>
    </div>
  );
}

/**
 * The intuition studio: the wizard on the left and the intuition on the right,
 * side by side and equally weighted. Starts from a conversation (new) or opens an
 * existing intuition with its latest conversation. The URL follows the model
 * once the wizard creates it, without remounting the chat mid-reply.
 */
export default function Studio({ modelId: initialModel = null, sessionId: initialSession = null }: { modelId?: string | null; sessionId?: string | null }) {
  const [modelId, setModelId] = useState<string | null>(initialModel);
  const [sessionId, setSessionId] = useState<string | null>(initialSession);
  const [detail, setDetail] = useState<ModelDetail | null>(null);
  const [report, setReport] = useState<TrainingReport | null>(null);
  // A brand-new intuition opens on How it works; an existing one on Setup.
  const [tab, setTab] = useState<Tab>(initialModel ? "setup" : "how");
  const [version, setVersion] = useState(0);
  const [inject, setInject] = useState<Injected | null>(null);
  const [mobile, setMobile] = useState<"wizard" | "model">("wizard");
  const [error, setError] = useState("");
  const refresh = useCallback(() => setVersion((v) => v + 1), []);
  // One layout at a time: the chat must mount once, or messages would be sent twice.
  const [desktop, setDesktop] = useState(true);
  useEffect(() => {
    const query = window.matchMedia("(min-width: 1024px)");
    const update = () => setDesktop(query.matches);
    update();
    query.addEventListener("change", update);
    return () => query.removeEventListener("change", update);
  }, []);

  // Find or start the conversation (once: dev double effects must not start two).
  const starting = useRef(false);
  useEffect(() => {
    if (sessionId) {
      if (!modelId) wzGet(sessionId).then((s) => { if (s.model_id) setModelId(s.model_id); }).catch((e) => setError(errorMessage(e)));
      return;
    }
    if (starting.current) return;
    starting.current = true;
    (async () => {
      try {
        const existing = modelId ? (await wzSessions()).sessions.find((s) => s.model_id === modelId) : undefined;
        const sid = existing?.id ?? (await wzCreate(modelId)).id;
        setSessionId(sid);
        if (!modelId) window.history.replaceState(null, "", `/reward-models/evals/new?session=${sid}`);
      } catch (e) { setError(errorMessage(e)); }
    })();
  }, [sessionId, modelId]);

  useEffect(() => {
    if (!modelId) return;
    Promise.all([imGet(modelId), wzReport(modelId)]).then(([d, r]) => { setDetail(d); setReport(r.report); }).catch((e) => setError(errorMessage(e)));
  }, [modelId, version]);

  const onModel = useCallback((id: string) => {
    setModelId(id);
    window.history.replaceState(null, "", `/reward-models/evals/${id}`);
  }, []);

  const ctx: WizardCtx = useMemo(() => ({
    modelId, refresh, version, busy: false,
    // Card events go to the conversation; requests from the right side do too.
    send: (text, kind = "message") => { refresh(); setInject({ id: Date.now(), text, kind }); if (kind === "message") setMobile("wizard"); },
  }), [modelId, refresh, version]);

  const counts = detail?.counts;
  const inbox = (counts?.inbox ?? 0) + (counts?.escalated ?? 0);
  const todo = counts?.needs_review ?? 0;
  const live = detail?.active;
  const headline = report?.holdout.accuracy != null
    ? `agrees with you ${pct(report.holdout.accuracy)} on ${report.holdout.n} held-out`
    : counts?.labeled ? `${counts.labeled} labeled · not trained yet` : "just started";

  const chat = (
    <div className="flex h-full min-h-0 flex-col border-border lg:border-r">
      {sessionId ? <WizardChat key={sessionId} sessionId={sessionId} embedded inject={inject} onRefresh={refresh} onModel={onModel} /> : <p className="p-4 text-xs text-muted-foreground">{error || "Starting the wizard…"}</p>}
    </div>
  );

  const pane = !modelId ? <Placeholder /> : (
    <div className="scroll-thin h-full min-h-0 overflow-y-auto">
      <div className="mx-auto max-w-4xl px-5 pt-4 pb-10">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div className="min-w-0">
            <Link href="/reward-models/evals" className="text-[11.5px] text-muted-foreground hover:underline">Intuitions /</Link>
            <h1 className="m-0 truncate text-lg font-semibold tracking-tight">{detail?.model.name ?? "…"}</h1>
            <p className="m-0 mt-0.5 text-[12.5px] text-muted-foreground">
              <span className={cn("mr-1.5 inline-block size-1.5 rounded-full align-middle", live ? "bg-emerald-500" : "bg-muted-foreground/50")} />
              {live ? `Live v${live.number}` : "Not live yet"} · {detail?.model.output_type === "multi" ? "multi-issue · " : ""}{headline}
            </p>
          </div>
          {detail && <UseIt detail={detail} onShipped={() => { refresh(); ctx.send(`Shipped version ${detail.draft?.number ?? ""} as the live intuition.`, "event"); }} />}
        </div>
        {error && <p role="alert" className="mt-2 text-xs text-destructive">{error}</p>}
        <nav role="tablist" aria-label="Intuition" className="scroll-thin mt-3 flex gap-0.5 overflow-x-auto border-b border-border">
          {TABS.map((t) => (
            <button key={t.id} role="tab" type="button" aria-selected={tab === t.id} onClick={() => setTab(t.id)} className={cn("-mb-px shrink-0 border-b-2 px-3 py-2 text-[13px]", tab === t.id ? "border-foreground font-medium" : "border-transparent text-muted-foreground hover:text-foreground")}>
              {t.label}
              {t.id === "inbox" && inbox > 0 && <span className="ml-1.5 rounded-full bg-brand-500 px-1.5 py-px text-[10.5px] font-semibold text-white tabular-nums">{inbox}</span>}
              {t.id === "golden" && (todo > 0 ? <span className="ml-1.5 rounded-full bg-amber-500/20 px-1.5 py-px text-[10.5px] text-amber-800 tabular-nums dark:text-amber-300">{todo}</span> : <span className="ml-1.5 text-[11px] text-muted-foreground tabular-nums">{counts?.labeled ?? ""}</span>)}
            </button>
          ))}
        </nav>
        <div className="mt-4">
          {tab === "setup" && detail && <SetupPanel detail={detail} onSaved={refresh} />}
          {tab === "golden" && <ExamplesPanel />}
          {tab === "inbox" && <InboxPanel />}
          {tab === "try" && detail && <div className="flex flex-col gap-4 [&>section]:my-0"><PlaygroundCard key={version} /><EvalEndpoint id={detail.model.id} outputType={detail.model.output_type} /></div>}
          {tab === "results" && <ResultsPanel />}
          {tab === "how" && <HowItWorks id={modelId} name={detail?.model.name ?? "my intuition"} />}
        </div>
      </div>
    </div>
  );

  return (
    <WizardProvider value={ctx}>
      {desktop ? (
        <ResizablePanelGroup orientation="horizontal" className="h-full min-h-0">
          <ResizablePanel defaultSize={42} minSize={28}>{chat}</ResizablePanel>
          <ResizableHandle withHandle />
          <ResizablePanel defaultSize={58} minSize={35}>{pane}</ResizablePanel>
        </ResizablePanelGroup>
      ) : (
        <div className="flex h-full min-h-0 flex-col">
          <div className="flex shrink-0 gap-1 border-b border-border p-1.5">
            {(["wizard", "model"] as const).map((m) => <button key={m} type="button" aria-pressed={mobile === m} onClick={() => setMobile(m)} className={cn("flex-1 rounded-md py-1.5 text-[12.5px]", mobile === m ? "bg-foreground text-background" : "text-muted-foreground")}>{m === "wizard" ? "Wizard" : detail?.model.name ?? "Intuition"}</button>)}
          </div>
          {/* Both stay mounted (hidden, not unmounted) so the chat keeps streaming while you look. */}
          <div className={cn("min-h-0 flex-1", mobile !== "wizard" && "hidden")}>{chat}</div>
          <div className={cn("min-h-0 flex-1", mobile !== "model" && "hidden")}>{pane}</div>
        </div>
      )}
    </WizardProvider>
  );
}
