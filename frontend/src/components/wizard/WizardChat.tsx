"use client";

import { useRouter } from "next/navigation";
import { tasteGet, tasteReset, type TasteWorkspace } from "@/lib/taste-api";
import { useCallback, useEffect, useLayoutEffect, useRef, useState } from "react";
import { ArrowUp, Check, CircleAlert, Loader2, Mic, Paperclip, RotateCcw, Sparkles, Square } from "lucide-react";
import Markdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { Button } from "@/components/ui/button";
import { evalSurfaceClass } from "@/components/evals/eval-ui";
import { cn } from "@/lib/utils";
import { errorMessage } from "@/components/reward-models/rm-text";
import { evalReadFile, imAddExamples, type NewExample } from "@/lib/intuition-api";
import { applyEvent, streamWizard, wzCreate, wzGet, type AssistantPart, type Card, type TranscriptEntry } from "@/lib/wizard-api";
import { WizardProvider, type WizardCtx } from "./wizard-ui";
import ModelPanel from "./ModelPanel";
import { useWizardDraft } from "./useWizardDraft";
import { useDictation } from "./useDictation";
import { takeWizardMessage } from "./wizard-navigation";
import { uploadWebsiteTraces } from "./website-traces";
import WebsiteEvalCard from "./cards/WebsiteEvalCard";
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
import RobustnessCard from "./cards/RobustnessCard";
import UploaderCard from "./cards/UploaderCard";

const STARTERS = [
  "Learn my website design preferences from my past sessions",
  "Build an eval from my past Codex sessions",
  "Check my coding agent's PRs before it opens them",
  "Grade my AI assistant's answers as good or bad",
  "Flag which brand guidelines a product photo breaks",
  "Route incoming support tickets to billing, bugs, or how-to",
];
const EVAL_STARTERS = [
  "Help me set up this eval.",
  "Find relevant examples in my past Codex sessions",
  "Review the current labels and criteria",
];

const TITLES: Record<Card["kind"], string> = {
  website_eval: "Your eval",
  choices: "Quick choices", uploader: "Add examples", labeler: "Label examples", criteria: "Criteria",
  report: "Training report", playground: "Try it", review: "Review predictions", robustness: "Robustness", examples: "Examples",
  brief: "Eval brief", inbox: "Inbox", golden: "Golden set", agreement: "Agreement", topics: "Topics",
};

/* eslint-disable @typescript-eslint/no-explicit-any -- card props are validated server-side by the tool schemas */
function CardView({ card, fresh = false }: { card: Card; fresh?: boolean }) {
  const p = card.props as any;
  switch (card.kind) {
    case "website_eval": return <WebsiteEvalCard section={p.section} jobId={p.jobId} exampleIds={p.exampleIds} />;
    case "choices": return <ChoicesCard question={p.question} options={p.options ?? []} multi={p.multi} />;
    case "uploader": return <UploaderCard prompt={p.prompt} />;
    case "labeler": return <LabelerCard which={p.which} fresh={fresh} />;
    case "criteria": return <CriteriaCard proposals={p.proposals} />;
    case "report": return <ReportCard />;
    case "playground": return <PlaygroundCard item={p.item} prediction={p.prediction} />;
    case "review": return <InboxCard />; // the review queue is the inbox now
    case "robustness": return <RobustnessCard result={p.result} />;
    case "examples": return <ExamplesCard />;
    case "brief": return <BriefCard />;
    case "inbox": return <InboxCard />;
    case "golden": return <GoldenCard />;
    case "agreement": return <AgreementCard invited={p.invited} />;
    case "topics": return <InboxCard />; // topics now live in the inbox
  }
}
/* eslint-enable @typescript-eslint/no-explicit-any */

/** Older cards of a kind collapse to one line (so only one labeler listens to the keyboard); reopen on demand. */
function CardSlot({ card, latest, fresh }: { card: Card; latest: boolean; fresh: boolean }) {
  const [open, setOpen] = useState(false);
  if (latest || open || card.kind === "robustness") return <CardView card={card} fresh={fresh && latest} />;
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
 * The wizard conversation. Workspace actions arrive once through session storage.
 * Embedded callers can hide its header/model panel and send messages via `inject`.
 */
export default function WizardChat({ sessionId, embedded = false, inject = null, onRefresh, onModel }: { sessionId: string; embedded?: boolean; inject?: Injected | null; onRefresh?: () => void; onModel?: (modelId: string, title: string) => void }) {
  const router = useRouter();
  const [entries, setEntries] = useState<TranscriptEntry[] | null>(null);
  const [modelId, setModelId] = useState<string | null>(null);
  const [title, setTitle] = useState("New eval");
  const [busy, setBusy] = useState(false);
  const [version, setVersion] = useState(0);
  const [website, setWebsite] = useState<TasteWorkspace | null>(null);
  const [resettingDemo, setResettingDemo] = useState(false);
  const draft = useWizardDraft(sessionId);
  const { input, setInput, load: loadDraft, flush: flushDraft, recover: recoverDraft } = draft;
  const [pending, setPending] = useState<Injected | null>(null);
  const [error, setError] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [restarting, setRestarting] = useState(false);
  const restartingRef = useRef(false);
  const submittingRef = useRef(false);
  const [attaching, setAttaching] = useState("");
  const queued = useRef<{ text: string; kind: "message" | "event" }[]>([]);
  const busyRef = useRef(false);
  // Cards that arrived live (not loaded from history): a labeler opens itself only then.
  const streamed = useRef(new Set<string>());
  const bottom = useRef<HTMLDivElement>(null);
  const fileInput = useRef<HTMLInputElement>(null);
  const messageInput = useRef<HTMLTextAreaElement>(null);
  const resizeInput = useCallback(() => {
    const area = messageInput.current;
    if (!area) return;
    area.style.height = "auto";
    area.style.height = `${area.scrollHeight}px`;
  }, []);
  useLayoutEffect(() => { resizeInput(); }, [input, resizeInput]);
  useEffect(() => {
    const area = messageInput.current;
    let width = area?.getBoundingClientRect().width;
    const observer = typeof ResizeObserver === "undefined" ? null : new ResizeObserver(([entry]) => {
      if (entry.contentRect.width !== width) { width = entry.contentRect.width; resizeInput(); }
    });
    if (area) observer?.observe(area);
    window.addEventListener("resize", resizeInput);
    return () => { observer?.disconnect(); window.removeEventListener("resize", resizeInput); };
  }, [resizeInput]);

  useEffect(() => {
    setPending(takeWizardMessage(sessionId));
    wzGet(sessionId).then((s) => {
      if (s.reset_to) { router.replace(`/reward-models/wizard/${s.reset_to}`); return; }
      if (s.status === "saved" && s.model_id) { router.replace(`/reward-models/evals/${s.model_id}`); return; }
      setEntries(s.transcript ?? []); setModelId(s.model_id); setTitle(s.model_name || s.title); loadDraft(s.draft_input ?? "");
    }).catch((e) => setError(errorMessage(e)));
  }, [sessionId, loadDraft, router]);
  useEffect(() => { let live = true; void tasteGet().then((w) => { if (live) setWebsite(w); }).catch(() => {}); return () => { live = false; }; }, [modelId, version, sessionId]);
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
        if (e.type === "card") streamed.current.add(e.id);
        if (e.type === "model") { setModelId(e.model_id); setTitle(e.title); onModel?.(e.model_id, e.title); }
        else if (e.type === "complete") { queued.current = []; router.replace(`/reward-models/evals/${e.model_id}`); }
        else if (e.type === "error") setError(e.message);
        else if (e.type === "done") refresh();
        patch((parts) => applyEvent(parts, e));
        if (e.type === "activity" && e.status !== "running") refresh();
      });
    } catch (e) {
      if (kind === "message") recoverDraft(text);
      setError(errorMessage(e));
    } finally {
      busyRef.current = false; setBusy(false);
      const next = queued.current.shift();
      if (next) void run(next.text, next.kind);
    }
  }, [sessionId, refresh, onModel, recoverDraft, router]);

  const send = useCallback((text: string, kind: "message" | "event" = "message") => {
    if (!text.trim() || restartingRef.current) return;
    if (busyRef.current) { queued.current.push({ text, kind }); return; }
    void run(text, kind);
  }, [run]);

  const dictation = useDictation(setInput);
  const restart = async () => {
    if (entries === null || busyRef.current || submittingRef.current || attaching || restartingRef.current) return;
    restartingRef.current = true; setRestarting(true); setError("");
    if (dictation.listening) dictation.stop();
    try {
      // Keep the old conversation and its unsent draft; only the new chat is empty.
      if (!await flushDraft()) return;
      const session = await wzCreate(modelId);
      router.replace(`/reward-models/wizard/${session.id}`);
    } catch (e) { setError(errorMessage(e)); }
    finally { restartingRef.current = false; setRestarting(false); }
  };
  const resetDemo = async () => {
    if (entries === null || busyRef.current || submittingRef.current || attaching || restartingRef.current) return;
    restartingRef.current = true; setRestarting(true); setResettingDemo(true); setError("");
    if (dictation.listening) dictation.stop();
    try {
      if (!await flushDraft()) return;
      const result = await tasteReset(sessionId);
      queued.current = [];
      router.replace(`/reward-models/wizard/${result.session_id}`);
    } catch (e) { setError(errorMessage(e)); }
    finally { restartingRef.current = false; setRestarting(false); setResettingDemo(false); }
  };
  const submit = async () => {
    if (!input.trim() || submittingRef.current || restartingRef.current) return;
    submittingRef.current = true; setSubmitting(true);
    if (dictation.listening) dictation.stop();
    const text = input;
    // Finish draft writes before submitting, so a late write cannot restore a sent message.
    try {
      if (!await flushDraft()) return;
      send(text); setInput("");
    } finally { submittingRef.current = false; setSubmitting(false); }
  };
  const injected = useRef(0);
  useEffect(() => {
    const message = inject ?? pending;
    if (!message || message.id === injected.current || entries === null) return;
    injected.current = message.id;
    send(message.text, message.kind);
  }, [inject, pending, entries, send]);

  async function attach(files: FileList) {
    if (Array.from(files).every(f => /\.jsonl$/i.test(f.name))) {
      setAttaching("Reading your traces…");
      try {
        const uploaded = await uploadWebsiteTraces(sessionId, Array.from(files).map((file) => ({ file, path: file.name })));
        setModelId(uploaded.modelId);
        send(uploaded.event, "event");
      } catch (e) { setError(errorMessage(e)); } finally { setAttaching(""); }
      return;
    }
    if (!modelId) { setError("Attach your exported JSONL traces, or describe what you want to judge first."); return; }
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

  const ctx: WizardCtx = { modelId, send, refresh, version, busy, sessionId, adoptModel: setModelId };
  const lastCardIds = new Map<string, string>();
  for (const entry of entries ?? []) if (entry.role === "assistant") for (const p of entry.parts) if (p.type === "card") { lastCardIds.set(p.kind, p.id); if(p.kind === "website_eval" && p.props.section === "preferences") lastCardIds.set("labeler",p.id); }

  return (
    <WizardProvider value={ctx}>
      <div className={cn(evalSurfaceClass, "flex h-full min-h-0 bg-background")}>
        <div className="flex min-w-0 flex-1 flex-col">
          {!embedded && (
            <header className="flex items-center gap-2 border-b border-border px-5 py-2.5">
              <h1 className="m-0 min-w-0 flex-1 truncate text-sm font-semibold">{title === "New model" ? "New eval" : title}</h1>
              <span className="hidden text-[11px] text-muted-foreground sm:inline" role="status">{draft.status === "Saved" ? "All changes saved" : draft.status}</span>
              <Button type="button" variant="ghost" size="sm" className="ml-auto shrink-0" disabled={entries === null || busy || submitting || !!attaching || restarting} onClick={() => void restart()} title="Start a fresh conversation. Your eval and previous chat are kept.">
                {restarting && !resettingDemo ? <Loader2 className="animate-spin" /> : <RotateCcw />} {restarting && !resettingDemo ? "Restarting…" : "Restart"}
              </Button>
              {website && (website.demo || (!!modelId && website.model_id === modelId) || (!modelId && website.fresh_start && website.wizard_session_id === sessionId)) && <Button type="button" variant="outline" size="sm" className="shrink-0" disabled={entries === null || busy || submitting || !!attaching || restarting} onClick={() => void resetDemo()} title="Start from scratch: archive this demo's chat, preferences, grader and results. Your original history is kept.">{resettingDemo ? <Loader2 className="animate-spin" /> : <RotateCcw />}{resettingDemo ? "Resetting…" : "Reset demo"}</Button>}
            </header>
          )}
          <div className="scroll-thin min-h-0 flex-1 overflow-y-auto">
            <div className="mx-auto max-w-3xl px-5 py-6">
              {entries && entries.length === 0 && (
                <div className="py-10 text-center">
                  <h2 className="m-0 text-lg font-semibold tracking-tight">{modelId ? "How can I help with this eval?" : "What judgment call should it make?"}</h2>
                  <p className="mx-auto mt-1 max-w-md text-[13px] text-muted-foreground">{modelId ? "This is a fresh conversation. Your eval’s existing examples, labels, and criteria are saved." : "Describe what you want to judge. The wizard finds relevant examples, learns from your feedback, and asks about anything unclear."}</p>
                  <div className="mx-auto mt-5 grid max-w-xl gap-2 sm:grid-cols-2">
                    {(modelId ? EVAL_STARTERS : STARTERS).map((s) => <button key={s} type="button" disabled={busy || restarting} onClick={() => send(s)} className="rounded border border-border px-3 py-2 text-left text-[12.5px] hover:bg-surface/60">{s}</button>)}
                  </div>
                </div>
              )}
              {entries?.map((entry, i) => entry.role === "user" ? (
                entry.kind === "event"
                  ? <div key={i} className="my-3 flex justify-end"><span className="rounded border border-border bg-surface/60 px-2.5 py-1 text-[11.5px] text-muted-foreground"><Check className="mr-1 inline size-3" />{entry.text}</span></div>
                  : <div key={i} className="my-4 flex justify-end"><div className="max-w-[80%] rounded bg-foreground px-3 py-2 text-[13px] whitespace-pre-wrap text-background">{entry.text}</div></div>
              ) : (
                <div key={i} className="my-3">
                  {entry.parts.map((part, j) => part.type === "text"
                    ? <div key={j} className="prose prose-sm max-w-none text-[13.5px] leading-relaxed dark:prose-invert [&_p]:my-1.5"><Markdown remarkPlugins={[remarkGfm]}>{part.text}</Markdown></div>
                    : part.type === "activity" ? <ActivityRow key={j} part={part} />
                      : <CardSlot key={part.id} card={part} latest={lastCardIds.get(part.kind) === part.id} fresh={streamed.current.has(part.id)} />)}
                  {busy && i === entries.length - 1 && entry.parts.length === 0 && <div className="flex items-center gap-2 text-[12px] text-muted-foreground"><Loader2 className="size-3.5 animate-spin" />Thinking…</div>}
                </div>
              ))}
              {draft.error && <p role="alert" className="text-[12px] text-destructive">{draft.error} <button type="button" className="underline" onClick={() => void flushDraft()}>Retry saving draft</button></p>}
              {error && <p role="alert" className="text-[12px] text-destructive">{error}</p>}
              <div ref={bottom} />
            </div>
          </div>
          <form className="shrink-0 border-t border-border px-5 py-3" onSubmit={(e) => { e.preventDefault(); void submit(); }}>
            <div className="mx-auto flex max-w-3xl items-end gap-2 rounded border border-border bg-background px-2 py-1.5 focus-within:border-foreground/30">
              <Button type="button" size="icon-sm" variant="ghost" aria-label="Attach examples" title="Upload traces or examples" disabled={!!attaching || restarting} onClick={() => fileInput.current?.click()}><Paperclip /></Button>
              <input ref={fileInput} type="file" multiple hidden accept=".jsonl,.txt,.md,.json,.pdf,.docx,.pptx,.png,.jpg,.jpeg,.webp,.gif" onChange={(e) => { if (e.target.files?.length) void attach(e.target.files); e.target.value = ""; }} />
              <textarea
                ref={messageInput}
                aria-label="Message the wizard"
                rows={1}
                disabled={submitting || restarting || entries === null}
                maxLength={20000}
                onBlur={() => { void flushDraft(); }}
                value={input}
                placeholder={modelId ? "Ask for anything: label more, add a criterion, train, try an input, ship…" : "Describe the decision your model should make…"}
                onChange={(e) => setInput(e.target.value)}
                onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) { e.preventDefault(); void submit(); } }}
                className="max-h-[min(20rem,40dvh)] min-h-8 min-w-0 flex-1 resize-none overflow-y-auto bg-transparent py-1.5 text-[13px] leading-5 outline-none"
              />
              {dictation.supported && (
                <Button type="button" size="icon-sm" variant={dictation.listening ? "default" : "ghost"} disabled={restarting} aria-label={dictation.listening ? "Stop voice input" : "Talk instead of typing"} aria-pressed={dictation.listening} title={dictation.listening ? "Listening… click to stop" : "Talk instead of typing"} onClick={() => (dictation.listening ? dictation.stop() : dictation.start(input))} className={dictation.listening ? "animate-pulse" : undefined}>
                  {dictation.listening ? <Square /> : <Mic />}
                </Button>
              )}
              <Button type="submit" size="icon-sm" aria-label="Send" disabled={submitting || restarting || !input.trim()}><ArrowUp /></Button>
            </div>
            {(attaching || dictation.listening || dictation.error || (busy && queued.current.length > 0)) && <p role="status" className="mx-auto mt-1 max-w-3xl text-[11px] text-muted-foreground">{attaching || dictation.error || (dictation.listening ? "Listening — talk it through; press Enter or the arrow to send." : "Queued until the wizard finishes.")}</p>}
          </form>
        </div>
        {!embedded && <ModelPanel modelId={modelId} version={version} />}
      </div>
    </WizardProvider>
  );
}
