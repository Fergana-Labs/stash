"use client";

import Link from "next/link";
import { useCallback, useEffect, useRef, useState } from "react";
import { ArrowUp, Check, CircleAlert, Loader2, Paperclip, Sparkles, Wand2 } from "lucide-react";
import Markdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { Button } from "@/components/ui/button";
import { errorMessage } from "@/components/reward-models/rm-text";
import { evalReadFile, imAddExamples, type NewExample } from "@/lib/intuition-api";
import { applyEvent, streamWizard, wzGet, type AssistantPart, type Card, type TranscriptEntry } from "@/lib/wizard-api";
import { WizardProvider, type WizardCtx } from "./wizard-ui";
import ModelPanel from "./ModelPanel";
import AgreementCard from "./cards/AgreementCard";
import BriefCard from "./cards/BriefCard";
import ChoicesCard from "./cards/ChoicesCard";
import CriteriaCard from "./cards/CriteriaCard";
import ExamplesCard from "./cards/ExamplesCard";
import GoldenCard from "./cards/GoldenCard";
import InboxCard from "./cards/InboxCard";
import LabelerCard from "./cards/LabelerCard";
import PlaygroundCard from "./cards/PlaygroundCard";
import ReportCard from "./cards/ReportCard";
import ReviewCard from "./cards/ReviewCard";
import RobustnessCard from "./cards/RobustnessCard";
import TopicsCard from "./cards/TopicsCard";
import UploaderCard from "./cards/UploaderCard";

const STARTERS = [
  "Route incoming support tickets to billing, bugs, or how-to",
  "Grade my AI assistant's answers as good or bad",
  "Flag product photos that break our brand guidelines",
  "Pick the better of two marketing email drafts",
];

const TITLES: Record<Card["kind"], string> = {
  choices: "Quick choices", uploader: "Add examples", labeler: "Label examples", criteria: "Criteria",
  report: "Training report", playground: "Try it", review: "Review predictions", robustness: "Robustness", examples: "Examples",
  brief: "Eval brief", inbox: "Inbox", golden: "Golden set", agreement: "Agreement", topics: "Topics",
};

/* eslint-disable @typescript-eslint/no-explicit-any -- card props are validated server-side by the tool schemas */
function CardView({ card }: { card: Card }) {
  const p = card.props as any;
  switch (card.kind) {
    case "choices": return <ChoicesCard question={p.question} options={p.options ?? []} multi={p.multi} />;
    case "uploader": return <UploaderCard prompt={p.prompt} />;
    case "labeler": return <LabelerCard which={p.which} />;
    case "criteria": return <CriteriaCard proposals={p.proposals} />;
    case "report": return <ReportCard />;
    case "playground": return <PlaygroundCard item={p.item} prediction={p.prediction} />;
    case "review": return <ReviewCard />;
    case "robustness": return <RobustnessCard result={p.result} />;
    case "examples": return <ExamplesCard />;
    case "brief": return <BriefCard />;
    case "inbox": return <InboxCard queue={p.queue} topic={p.topic} />;
    case "golden": return <GoldenCard />;
    case "agreement": return <AgreementCard invited={p.invited} />;
    case "topics": return <TopicsCard />;
  }
}
/* eslint-enable @typescript-eslint/no-explicit-any */

/** Older cards of a kind collapse to one line (so only one labeler listens to the keyboard); reopen on demand. */
function CardSlot({ card, latest }: { card: Card; latest: boolean }) {
  const [open, setOpen] = useState(false);
  if (latest || open || card.kind === "robustness") return <CardView card={card} />;
  return (
    <button type="button" onClick={() => setOpen(true)} className="my-1 flex w-full items-center gap-2 rounded-md border border-dashed border-border px-3 py-1.5 text-left text-[12px] text-muted-foreground hover:bg-surface/60">
      <Sparkles className="size-3" />{TITLES[card.kind]} <span className="ml-auto underline">Reopen</span>
    </button>
  );
}

function ActivityRow({ part }: { part: Extract<AssistantPart, { type: "activity" }> }) {
  return (
    <div className="my-1 flex items-center gap-2 text-[12px] text-muted-foreground">
      {part.status === "running" ? <Loader2 className="size-3.5 animate-spin" /> : part.status === "done" ? <Check className="size-3.5 text-emerald-600" /> : <CircleAlert className="size-3.5 text-red-500" />}
      <span>{part.label}{part.status === "running" && part.progress ? ` — ${part.progress}` : ""}{part.status === "error" && part.error ? ` — ${part.error}` : ""}</span>
    </div>
  );
}

export interface Injected { id: number; text: string; kind: "message" | "event" }

/**
 * The wizard conversation. Embedded (in the eval page's drawer) it drops its own
 * header and model panel, takes messages from the page via `inject`, and tells
 * the page to reload via `onRefresh`.
 */
export default function WizardChat({ sessionId, embedded = false, inject = null, onRefresh }: { sessionId: string; embedded?: boolean; inject?: Injected | null; onRefresh?: () => void }) {
  const [entries, setEntries] = useState<TranscriptEntry[] | null>(null);
  const [modelId, setModelId] = useState<string | null>(null);
  const [title, setTitle] = useState("New eval");
  const [busy, setBusy] = useState(false);
  const [version, setVersion] = useState(0);
  const [input, setInput] = useState("");
  const [error, setError] = useState("");
  const [attaching, setAttaching] = useState("");
  const queued = useRef<{ text: string; kind: "message" | "event" }[]>([]);
  const busyRef = useRef(false);
  const bottom = useRef<HTMLDivElement>(null);
  const fileInput = useRef<HTMLInputElement>(null);

  useEffect(() => {
    wzGet(sessionId).then((s) => { setEntries(s.transcript ?? []); setModelId(s.model_id); setTitle(s.title); }).catch((e) => setError(errorMessage(e)));
  }, [sessionId]);
  useEffect(() => { bottom.current?.scrollIntoView({ behavior: "smooth", block: "end" }); }, [entries]);

  const refresh = useCallback(() => { setVersion((v) => v + 1); onRefresh?.(); }, [onRefresh]);

  const run = useCallback(async (text: string, kind: "message" | "event") => {
    busyRef.current = true; setBusy(true); setError("");
    setEntries((prev) => [...(prev ?? []), { role: "user", kind, text }, { role: "assistant", parts: [] }]);
    const patch = (fn: (parts: AssistantPart[]) => AssistantPart[]) => setEntries((prev) => {
      if (!prev) return prev;
      const last = prev[prev.length - 1];
      if (last?.role !== "assistant") return prev;
      return [...prev.slice(0, -1), { ...last, parts: fn(last.parts) }];
    });
    try {
      await streamWizard(sessionId, text, kind, (e) => {
        if (e.type === "model") { setModelId(e.model_id); setTitle(e.title); }
        else if (e.type === "error") setError(e.message);
        else if (e.type === "done") refresh();
        patch((parts) => applyEvent(parts, e));
        if (e.type === "activity" && e.status !== "running") refresh();
      });
    } catch (e) {
      setError(errorMessage(e));
    } finally {
      busyRef.current = false; setBusy(false);
      const next = queued.current.shift();
      if (next) void run(next.text, next.kind);
    }
  }, [sessionId, refresh]);

  const send = useCallback((text: string, kind: "message" | "event" = "message") => {
    if (!text.trim()) return;
    if (busyRef.current) { queued.current.push({ text, kind }); return; }
    void run(text, kind);
  }, [run]);

  const injected = useRef(0);
  useEffect(() => {
    if (!inject || inject.id === injected.current || entries === null) return;
    injected.current = inject.id;
    send(inject.text, inject.kind);
  }, [inject, entries, send]);

  async function attach(files: FileList) {
    if (!modelId) { setError("Tell the wizard what you want to classify first, then attach examples."); return; }
    const rows: NewExample[] = [];
    try {
      for (const [i, file] of Array.from(files).entries()) {
        setAttaching(`Reading ${file.name} (${i + 1}/${files.length})…`);
        rows.push({ item: await evalReadFile(file), needs_review: true });
      }
      await imAddExamples(modelId, rows);
      refresh();
      send(`Attached ${rows.length} file${rows.length === 1 ? "" : "s"} as unlabeled examples.`, "event");
    } catch (e) { setError(errorMessage(e)); } finally { setAttaching(""); }
  }

  const ctx: WizardCtx = { modelId, send, refresh, version, busy };
  const lastCardIds = new Map<string, string>();
  for (const entry of entries ?? []) if (entry.role === "assistant") for (const p of entry.parts) if (p.type === "card") lastCardIds.set(p.kind, p.id);

  return (
    <WizardProvider value={ctx}>
      <div className="flex h-full min-h-0">
        <div className="flex min-w-0 flex-1 flex-col">
          {!embedded && (
            <header className="flex items-center gap-2 border-b border-border px-5 py-2.5">
              <Link href="/reward-models/wizard" className="text-xs text-muted-foreground hover:underline">Eval wizard /</Link>
              <h1 className="m-0 truncate text-sm font-semibold">{title === "New model" ? "New eval" : title}</h1>
              {modelId && <Link href={`/reward-models/evals/${modelId}`} className="ml-auto text-xs text-muted-foreground hover:underline">Open eval page →</Link>}
            </header>
          )}
          <div className="scroll-thin min-h-0 flex-1 overflow-y-auto">
            <div className="mx-auto max-w-3xl px-5 py-6">
              {entries && entries.length === 0 && (
                <div className="py-10 text-center">
                  <div className="mx-auto mb-3 grid size-11 place-items-center rounded-xl bg-brand-500/10 text-brand-600 dark:text-brand-400"><Wand2 className="size-5" /></div>
                  <h2 className="m-0 text-lg font-semibold tracking-tight">What should your model decide?</h2>
                  <p className="mx-auto mt-1 max-w-md text-[13px] text-muted-foreground">Describe the judgment call. The wizard sets up labels and criteria with you, helps you label a handful of examples — text, images, or documents — and trains a calibrated model you can test, harden, and ship.</p>
                  <div className="mx-auto mt-5 grid max-w-xl gap-2 sm:grid-cols-2">
                    {STARTERS.map((s) => <button key={s} type="button" disabled={busy} onClick={() => send(s)} className="rounded-lg border border-border px-3 py-2.5 text-left text-[12.5px] hover:bg-surface/60">{s}</button>)}
                  </div>
                </div>
              )}
              {entries?.map((entry, i) => entry.role === "user" ? (
                entry.kind === "event"
                  ? <div key={i} className="my-3 flex justify-end"><span className="rounded-full border border-border bg-surface/60 px-2.5 py-1 text-[11.5px] text-muted-foreground"><Check className="mr-1 inline size-3" />{entry.text}</span></div>
                  : <div key={i} className="my-4 flex justify-end"><div className="max-w-[80%] rounded-2xl rounded-br-sm bg-foreground px-3.5 py-2 text-[13px] whitespace-pre-wrap text-background">{entry.text}</div></div>
              ) : (
                <div key={i} className="my-3">
                  {entry.parts.map((part, j) => part.type === "text"
                    ? <div key={j} className="prose prose-sm max-w-none text-[13.5px] leading-relaxed dark:prose-invert [&_p]:my-1.5"><Markdown remarkPlugins={[remarkGfm]}>{part.text}</Markdown></div>
                    : part.type === "activity" ? <ActivityRow key={j} part={part} />
                      : <CardSlot key={part.id} card={part} latest={lastCardIds.get(part.kind) === part.id} />)}
                  {busy && i === entries.length - 1 && entry.parts.length === 0 && <div className="flex items-center gap-2 text-[12px] text-muted-foreground"><Loader2 className="size-3.5 animate-spin" />Thinking…</div>}
                </div>
              ))}
              {error && <p role="alert" className="text-[12px] text-destructive">{error}</p>}
              <div ref={bottom} />
            </div>
          </div>
          <form className="border-t border-border px-5 py-3" onSubmit={(e) => { e.preventDefault(); send(input); setInput(""); }}>
            <div className="mx-auto flex max-w-3xl items-end gap-2 rounded-xl border border-border bg-background px-2 py-1.5 focus-within:border-foreground/30">
              <Button type="button" size="icon-sm" variant="ghost" aria-label="Attach examples" title={modelId ? "Attach files as examples (images, PDFs, docs)" : "Describe your model first"} disabled={!!attaching} onClick={() => fileInput.current?.click()}><Paperclip /></Button>
              <input ref={fileInput} type="file" multiple hidden accept=".txt,.md,.json,.pdf,.docx,.pptx,.png,.jpg,.jpeg,.webp,.gif" onChange={(e) => { if (e.target.files?.length) void attach(e.target.files); e.target.value = ""; }} />
              <textarea
                aria-label="Message the wizard"
                rows={1}
                value={input}
                placeholder={modelId ? "Ask for anything: label more, add a criterion, train, try an input, ship…" : "Describe the decision your model should make…"}
                onChange={(e) => setInput(e.target.value)}
                onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) { e.preventDefault(); send(input); setInput(""); } }}
                className="max-h-40 min-h-8 flex-1 resize-none bg-transparent py-1.5 text-[13px] outline-none"
              />
              <Button type="submit" size="icon-sm" aria-label="Send" disabled={!input.trim()}><ArrowUp /></Button>
            </div>
            {(attaching || (busy && queued.current.length > 0)) && <p role="status" className="mx-auto mt-1 max-w-3xl text-[11px] text-muted-foreground">{attaching || "Queued until the wizard finishes."}</p>}
          </form>
        </div>
        {!embedded && <ModelPanel modelId={modelId} version={version} />}
      </div>
    </WizardProvider>
  );
}
