"use client";

import { Fragment, useEffect, useMemo, useRef, useState } from "react";
import { ArrowLeft, ArrowRight, X } from "lucide-react";
import { toast } from "sonner";
import type { RmStep } from "@/lib/types";
import { cn } from "@/lib/utils";
import AnchoredText from "./AnchoredText";
import { readableExcerpt } from "./trace-presentation";
import type { Highlight } from "./source-anchors";

/** Raw message text is never cleaned, truncated, or reclassified by role. */
function messageText(step: RmStep): string {
  return step.tool_input === null ? step.content : [step.content, JSON.stringify(step.tool_input, null, 2)].filter(Boolean).join("\n\n");
}

function searchPattern(query: string): RegExp {
  // Escaping keeps search literal; RegExp indices retain original Unicode offsets.
  return new RegExp(query.replace(/[.*+?^${}()|[\]\\]/g, "\\$&"), "giu");
}

function matches(text: string, query: string): Highlight[] {
  if (!query) return [];
  const pattern = searchPattern(query);
  return [...text.matchAll(pattern)].map((match, i) => ({
    id: `match-${i}`, start: match.index, end: match.index + match[0].length,
    className: "bg-yellow-200 text-inherit dark:bg-yellow-500/30",
  }));
}

const control = "inline-flex size-7 shrink-0 cursor-pointer items-center justify-center rounded hover:bg-surface disabled:cursor-default disabled:opacity-30";

export default function TraceMessageReader({ steps, stepId, numberOf, onClose, onReveal }: {
  steps: RmStep[];
  stepId: string;
  numberOf: (step: RmStep) => number | undefined;
  onClose: () => void;
  onReveal: (id: string) => void;
}) {
  const [selectedId, setSelectedId] = useState(stepId);
  const [query, setQuery] = useState("");
  const [role, setRole] = useState("");
  const [mode, setMode] = useState<"rendered" | "raw">("rendered");
  const [copied, setCopied] = useState(false);
  const [matchIndex, setMatchIndex] = useState(0);
  const panel = useRef<HTMLElement>(null);
  const content = useRef<HTMLDivElement>(null);
  const copyTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const roles = [...new Set(steps.map((step) => step.role))];
  const candidates = useMemo(() => steps.filter((step) => (!role || step.role === role) && (!query || searchPattern(query).test(messageText(step)))), [steps, role, query]);
  const step = candidates.find((item) => item.id === selectedId) ?? candidates[0];
  const index = step ? candidates.indexOf(step) : -1;
  const text = step ? messageText(step) : "";
  const highlights = useMemo(() => matches(text, query), [text, query]);
  const activeMatch = highlights.length ? matchIndex % highlights.length : 0;

  useEffect(() => {
    const opener = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    panel.current?.focus({ preventScroll: true });
    return () => {
      if (copyTimer.current) clearTimeout(copyTimer.current);
      if (opener?.isConnected) opener.focus({ preventScroll: true });
    };
  }, []);

  useEffect(() => {
    const mark = content.current?.querySelector(`[data-ids="match-${activeMatch}"]`);
    if (mark) mark.scrollIntoView({ block: "nearest" });
    else content.current?.scrollTo({ top: 0 });
  }, [step?.id, query, mode, activeMatch]);

  function select(id: string) {
    setMatchIndex(0);
    setCopied(false);
    setSelectedId(id);
  }

  async function copy() {
    try {
      await navigator.clipboard.writeText(text);
      setCopied(true);
      if (copyTimer.current) clearTimeout(copyTimer.current);
      copyTimer.current = setTimeout(() => setCopied(false), 1200);
    } catch { toast.error("Couldn’t copy this message."); }
  }

  return <aside ref={panel} tabIndex={-1} aria-label="Message reader"
    onKeyDown={(event) => { if (event.key === "Escape") { event.stopPropagation(); onClose(); } }}
    className="absolute inset-y-0 right-0 z-30 flex w-full min-h-0 flex-col border-l border-border bg-background outline-none lg:static lg:w-[min(46vw,36rem)] lg:shrink-0">
    <div className="shrink-0 space-y-2 border-b border-border px-4 py-3">
      <div className="flex items-center gap-2">
        <h2 className="m-0 flex-1 text-sm font-semibold">Messages</h2>
        <button type="button" onClick={onClose} className={control} aria-label="Close message reader"><X className="size-4" /></button>
      </div>
      <div className="flex gap-2">
        <input type="search" aria-label="Search messages" placeholder="Search messages…" value={query}
          onChange={(event) => { setQuery(event.target.value); setMatchIndex(0); if (event.target.value) setMode("raw"); }}
          onKeyDown={(event) => { if (event.key === "Enter" && highlights.length) { event.preventDefault(); setMatchIndex((value) => (value + (event.shiftKey ? highlights.length - 1 : 1)) % highlights.length); } }}
          className="h-8 min-w-0 flex-1 rounded-md border border-border bg-background px-2 text-xs" />
        <select aria-label="Message role" value={role} onChange={(event) => { setRole(event.target.value); setMatchIndex(0); }} className="h-8 rounded-md border border-border bg-background px-2 text-xs">
          <option value="">All roles</option>
          {roles.map((value) => <option key={value} value={value}>{value[0].toUpperCase() + value.slice(1)}</option>)}
        </select>
      </div>
      <div className="flex items-center gap-1">
        <select aria-label="Choose message" value={step?.id ?? ""} onChange={(event) => select(event.target.value)} disabled={!step} className="h-8 min-w-0 flex-1 truncate rounded-md border border-border bg-background px-2 text-xs">
          {!step && <option value="">No matching messages</option>}
          {candidates.map((item) => <option key={item.id} value={item.id}>Step {numberOf(item)} · {item.role}{item.tool_name ? ` · ${item.tool_name}` : ""} · {readableExcerpt(messageText(item), 90)}</option>)}
        </select>
        <button type="button" aria-label="Previous message" className={control} disabled={index <= 0} onClick={() => select(candidates[index - 1].id)}><ArrowLeft className="size-3.5" /></button>
        <button type="button" aria-label="Next message" className={control} disabled={index < 0 || index >= candidates.length - 1} onClick={() => select(candidates[index + 1].id)}><ArrowRight className="size-3.5" /></button>
      </div>
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-[11px] text-muted-foreground">
        <span role="status">{index < 0 ? 0 : index + 1} of {candidates.length} messages</span>
        {highlights.length > 0 && <button type="button" className="cursor-pointer hover:text-foreground" onClick={() => { setMode("raw"); setMatchIndex((value) => value + 1); }}>Match {activeMatch + 1} of {highlights.length}</button>}
        <span className="flex-1" />
        {step && <button type="button" className="cursor-pointer hover:text-foreground" onClick={() => onReveal(step.id)}>Show in trace</button>}
      </div>
    </div>
    {step ? <>
      <div className="flex shrink-0 items-center gap-3 px-4 py-2 text-xs">
        <span className="font-medium capitalize">{step.role}</span>
        <span className="text-muted-foreground">Step {numberOf(step)}</span>
        <span className="flex-1" />
        {(["rendered", "raw"] as const).map((value) => <button type="button" key={value} aria-pressed={mode === value} onClick={() => setMode(value)}
          className={cn("cursor-pointer border-b-2 py-1 capitalize", mode === value ? "border-foreground" : "border-transparent text-muted-foreground")}>{value === "raw" ? "Raw" : "Rendered"}</button>)}
        <button type="button" onClick={() => void copy()} className="cursor-pointer text-muted-foreground hover:text-foreground" aria-label="Copy raw message">{copied ? "Copied" : "Copy"}</button>
      </div>
      <div ref={content} className="scroll-thin min-h-0 flex-1 overflow-y-auto break-words px-4 pb-8" aria-label="Message content">
        {mode === "raw" ? <pre className="m-0 whitespace-pre-wrap break-words font-mono text-xs leading-relaxed">{highlights.map((match, i) => <Fragment key={match.id}>
          {text.slice(i === 0 ? 0 : highlights[i - 1].end, match.start)}
          <mark data-ids={match.id} className={cn("bg-yellow-200 text-inherit dark:bg-yellow-500/30", i === activeMatch && "outline outline-1 outline-amber-500")}>{text.slice(match.start, match.end)}</mark>
        </Fragment>)}{text.slice(highlights.at(-1)?.end ?? 0)}</pre>
          : <>
            {query && <p className="mb-3 text-xs text-muted-foreground">Search includes raw text. <button type="button" onClick={() => setMode("raw")} className="cursor-pointer underline">View all matches</button></p>}
            <AnchoredText stepId={`reader-${step.id}`} content={text} images={step.images} markdown={step.role !== "tool"} highlights={highlights} onSelectAnnotation={() => {}} />
          </>}
      </div>
    </> : <p className="p-4 text-sm text-muted-foreground">No messages match your search.</p>}
  </aside>;
}
