"use client";

import { useState, type ReactNode } from "react";
import { FileText } from "lucide-react";
import Markdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { cn } from "@/lib/utils";
import type { Item } from "@/lib/intuition-api";
import { readableText } from "./im-helpers";
import { Dialog, DialogContent, DialogTitle } from "@/components/ui/dialog";

const LONG = 240;
/** Field pairs that read as a conversation: who asked, then who answered. */
const TURNS: [string, string][] = [
  ["question", "answer"], ["customer", "reply"], ["prompt", "response"], ["input", "output"],
  ["query", "response"], ["user", "assistant"], ["message", "reply"], ["ticket", "response"],
];
const FILE_KEYS = new Set(["kind", "name", "content", "data_url", "extraction"]);
const IMAGE = /^data:image\/(png|jpeg|webp|gif);base64,/;

const humanize = (key: string) => key.replace(/[_-]+/g, " ").replace(/^\w/, (c) => c.toUpperCase());

function parse(item: Item): Item {
  if (typeof item !== "string") return item;
  const text = item.trim();
  if (text.startsWith("{") && text.endsWith("}")) {
    try { const parsed = JSON.parse(text); if (parsed && typeof parsed === "object" && !Array.isArray(parsed)) return parsed as Record<string, unknown>; } catch { /* plain text */ }
  }
  return item;
}

function Clamp({ text, clamp, className }: { text: string; clamp: boolean; className?: string }) {
  const [open, setOpen] = useState(false);
  const long = clamp && (text.length > LONG || text.split("\n").length > 4);
  return (
    <div className="min-w-0">
      <p className={cn("m-0 text-[12.5px] leading-relaxed break-words whitespace-pre-wrap text-foreground", long && !open && "line-clamp-3", className)}>{text || <span className="text-muted-foreground italic">empty</span>}</p>
      {long && <button type="button" onClick={() => setOpen((v) => !v)} className="text-[11.5px] text-muted-foreground underline decoration-border underline-offset-2 hover:text-foreground">{open ? "Show less" : "Show more"}</button>}
    </div>
  );
}

function Bubble({ who, side, children }: { who: string; side: "in" | "out"; children: ReactNode }) {
  return (
    <div className={cn("flex min-w-0 flex-col", side === "out" && "items-end")}>
      <span className="mb-0.5 text-[10.5px] text-muted-foreground">{who}</span>
      <div className={cn("max-w-[92%] min-w-0 rounded-xl px-3 py-1.5", side === "in" ? "rounded-tl-sm bg-raised" : "rounded-tr-sm bg-brand-500/10")}>{children}</div>
    </div>
  );
}

/** An uploaded file: the image itself (or the file name), with what the judge reads one click away. */
function FileItem({ item }: { item: Record<string, unknown> }) {
  const [open, setOpen] = useState(false);
  const [preview, setPreview] = useState(false);
  const name = typeof item.name === "string" ? item.name : item.kind === "image" ? "Image" : "Document";
  const image = typeof item.data_url === "string" && IMAGE.test(item.data_url) ? item.data_url : null;
  const content = typeof item.content === "string" ? item.content : "";
  return (
    <div className="min-w-0 space-y-1.5">
      {/* Inline data previews belong to the saved input. */}
      {/* eslint-disable-next-line @next/next/no-img-element */}
      {image ? <><button type="button" className="block cursor-zoom-in text-left" aria-label={`Enlarge ${name}`} onClick={() => setPreview(true)}><img src={image} alt={name} className="max-h-64 max-w-full rounded-md border border-border object-contain" /></button><Dialog open={preview} onOpenChange={setPreview}><DialogContent className="max-h-[94vh] w-[95vw] overflow-auto sm:max-w-[95vw]"><DialogTitle className="sr-only">{name}</DialogTitle><img src={image} alt={name} className="mx-auto max-h-[84vh] max-w-full object-contain" /></DialogContent></Dialog></> : (
        <div className="flex items-center gap-2 text-[12.5px]"><FileText className="size-4 text-muted-foreground" />{name}</div>
      )}
      {content && (
        <>
          <button type="button" onClick={() => setOpen((v) => !v)} className="block text-[11.5px] text-muted-foreground underline decoration-border underline-offset-2 hover:text-foreground">
            {open ? "Hide" : item.kind === "image" ? "What the judge sees" : "Show text"}
          </button>
          {open && <div className="prose prose-sm max-h-72 max-w-none overflow-y-auto rounded-md border border-border bg-surface/40 px-3 py-2 text-[12px] dark:prose-invert [&_h1]:text-[13px] [&_h2]:text-[12.5px] [&_h3]:text-[12px]"><Markdown remarkPlugins={[remarkGfm]}>{content}</Markdown></div>}
        </>
      )}
    </div>
  );
}

/** An agent's steps, collapsed behind their count. */
function Steps({ steps }: { steps: string[] }) {
  const [open, setOpen] = useState(false);
  return (
    <div className="min-w-0">
      <button type="button" onClick={() => setOpen((v) => !v)} className="text-[11.5px] text-muted-foreground underline decoration-border underline-offset-2 hover:text-foreground">
        {open ? "Hide" : `${steps.length} agent step${steps.length === 1 ? "" : "s"}`}
      </button>
      {open && (
        <ol className="m-0 mt-1 max-h-72 list-none space-y-1 overflow-y-auto rounded-md border border-border bg-surface/40 px-3 py-2 font-mono text-[11px] leading-relaxed">
          {steps.map((step, i) => <li key={i} className="break-words whitespace-pre-wrap">{step}</li>)}
        </ol>
      )}
    </div>
  );
}

/**
 * Read-only rendering of an input, made for people rather than JSON: uploaded
 * files as the file, question/answer-shaped objects as a conversation, chat
 * transcripts as bubbles, other objects as labeled fields, text as text.
 */
export default function ItemView({ item: raw, clamp = true, className }: { item: Item; clamp?: boolean; className?: string }) {
  const item = parse(raw);
  if (typeof item === "string") {
    const qa = /^\s*Q:\s*([\s\S]*?)\n?\s*A:\s*([\s\S]*)$/.exec(item);
    if (qa) {
      return <div className={cn("min-w-0 space-y-1.5", className)}><Bubble who="Question" side="in"><Clamp text={qa[1].trim()} clamp={clamp} /></Bubble><Bubble who="Answer" side="out"><Clamp text={qa[2].trim()} clamp={clamp} /></Bubble></div>;
    }
    return <div className={cn("min-w-0", className)}><Clamp text={item} clamp={clamp} /></div>;
  }
  if ((item.kind === "image" || item.kind === "document") && Object.keys(item).every((k) => FILE_KEYS.has(k))) {
    return <div className={className}><FileItem item={item} /></div>;
  }
  if (item.kind === "history" && item.source && typeof item.source === "object" && Array.isArray(item.events)) {
    const source = item.source as Record<string, unknown>;
    const events = item.events.filter((e): e is { index: number; role: string; content: string; tool_name?: string } =>
      e && typeof e === "object" && typeof e.index === "number" && typeof e.role === "string" && typeof e.content === "string" && (e.tool_name === undefined || typeof e.tool_name === "string"));
    const url = typeof source.url === "string" && /^\/(?:sessions\/|reward-models\/traces\/)/.test(source.url) ? source.url : null;
    return <div className={cn("min-w-0 space-y-3", className)}>
      <div className="border-b border-border pb-2">
        <p className="m-0 text-xs font-medium text-foreground">{typeof source.title === "string" ? source.title : "Past session"}</p>
        <p className="mt-1 text-[11px] text-muted-foreground">{source.kind === "local" ? "Local Codex session" : "Recorded session"}, Excerpt{typeof item.offset === "number" && typeof item.end_offset === "number" ? `, turns ${item.offset + 1}–${item.end_offset}` : ""}</p>
        {url && <a className="text-[11px] text-muted-foreground underline" href={url}>Open session</a>}
      </div>
      <div className="max-h-[460px] space-y-2 overflow-y-auto">
        {events.map((event) => <Bubble key={event.index} who={event.tool_name ?? (event.role === "user" ? "You" : event.role === "tool" ? "Tool result" : "Agent")} side={event.role === "user" ? "out" : "in"}><Clamp text={event.content} clamp={clamp} /></Bubble>)}
      </div>
      {Boolean(item.content_truncated || item.partial_history) && <p className="text-[11px] text-muted-foreground">{item.content_truncated ? "Some long messages are shortened. " : ""}{item.partial_history ? "Earlier resumed turns are unavailable in this excerpt." : ""}</p>}
    </div>;
  }
  if (typeof item.request === "string" && "output" in item) {
    const output = item.output;
    const steps = Array.isArray(item.trace) ? item.trace.map((step) => readableText(step)) : [];
    return <div className={cn("min-w-0 space-y-2", className)}>
      <Bubble who="Request" side="out"><Clamp text={item.request} clamp={clamp} /></Bubble>
      {steps.length > 0 && <Steps steps={steps} />}
      <Bubble who="Agent output" side="in">{output && typeof output === "object" && !Array.isArray(output) && "kind" in output ? <FileItem item={output as Record<string, unknown>} /> : <Clamp text={readableText(output)} clamp={clamp} />}</Bubble>
      {typeof item.source === "string" && <p className="m-0 text-[11px] text-muted-foreground">{item.source}</p>}
    </div>;
  }
  const messages = Array.isArray(item.messages) ? (item.messages as { role?: string; content?: unknown }[]) : null;
  const keys = Object.keys(item);
  const pair = TURNS.find(([a, b]) => keys.includes(a) && keys.includes(b));
  const rest = keys.filter((k) => k !== "messages" && k !== "data_url" && !(pair && pair.includes(k)));
  return (
    <div className={cn("min-w-0 space-y-2", className)}>
      {messages && (
        <div className="space-y-1.5">
          {messages.map((m, i) => <Bubble key={i} who={humanize(String(m.role ?? "message"))} side={m.role === "assistant" ? "out" : "in"}><Clamp text={readableText(m.content)} clamp={clamp} /></Bubble>)}
        </div>
      )}
      {pair && (
        <div className="space-y-1.5">
          <Bubble who={humanize(pair[0])} side="in"><Clamp text={readableText(item[pair[0]])} clamp={clamp} /></Bubble>
          <Bubble who={humanize(pair[1])} side="out"><Clamp text={readableText(item[pair[1]])} clamp={clamp} /></Bubble>
        </div>
      )}
      {rest.length > 0 && (
        <dl className="m-0 space-y-1.5">
          {rest.map((key) => (
            <div key={key} className="min-w-0">
              <dt className="text-[11px] font-medium text-muted-foreground">{humanize(key)}</dt>
              <dd className="m-0"><Clamp text={readableText(item[key])} clamp={clamp} /></dd>
            </div>
          ))}
        </dl>
      )}
    </div>
  );
}
