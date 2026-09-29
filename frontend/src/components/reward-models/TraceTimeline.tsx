// Design from Priyadarshan's trace viewer (projects/trace_viewer)
"use client";

import { useLayoutEffect, useRef, useState, type ReactNode } from "react";
import { Bot, Brain, Check, ChevronDown, ChevronRight, Cog, Copy, MessageSquarePlus, User } from "lucide-react";
import { cn } from "@/lib/utils";
import type { RmStep } from "@/lib/types";
import AnchoredText from "./AnchoredText";
import ToolIcon from "./ToolIcon";
import { RatingButton } from "./rm-ui";
import { firstLine, isThinking, looksLikeError, toolFamily, toolLabel, toolSummary, type TraceRow } from "./trace-rows";
import type { Highlight } from "./source-anchors";

/** The reward model never sees system steps, so the server rejects ratings on them. Comments are still allowed. */
export function isRateable(step: RmStep): boolean {
  return step.role !== "system";
}

export interface StepRatingState {
  positive: number;
  negative: number;
  mine: 1 | -1 | null;
  pending: 1 | -1 | null;
}

/** Everything a row needs to show and change one step's annotations. Built once per render by the trace page. */
export interface StepAnnotations {
  highlights: (step: RmStep) => Highlight[];
  rating: (step: RmStep) => StepRatingState;
  commentCount: (step: RmStep) => number;
  hasQuotes: (step: RmStep) => boolean;
  flashing: (step: RmStep) => boolean;
  onRate: (step: RmStep, rating: 1 | -1) => void;
  onComment: (step: RmStep, anchor: HTMLElement) => void;
  onSelectAnnotation: (ids: string[]) => void;
}

type Tone = "user" | "asst" | "tool" | "sys" | "err" | "think";

const NODE_TONE: Record<Tone, string> = {
  user: "border-amber-300/60 bg-amber-50 text-amber-800 dark:bg-amber-400/15 dark:text-amber-300",
  asst: "border-foreground bg-foreground text-background",
  tool: "border-border bg-background text-dim",
  sys: "border-slate-300/60 bg-slate-100 text-slate-500 dark:bg-slate-400/15 dark:text-slate-300",
  err: "border-red-300/60 bg-red-50 text-red-600 dark:bg-red-500/15 dark:text-red-400",
  think: "border-violet-300/50 bg-violet-50 text-violet-600 dark:bg-violet-400/15 dark:text-violet-300",
};

function Node({ tone, children }: { tone: Tone; children: ReactNode }) {
  return (
    <span className={cn("absolute top-[3px] left-0 grid size-[22px] place-items-center rounded-full border", NODE_TONE[tone])}>
      {children}
    </span>
  );
}

/** Row frame: the timeline node sits in the left gutter; the id is the scroll target for click-to-scroll. */
function RowFrame({ step, flashing, children, className }: { step: RmStep; flashing: boolean; children: ReactNode; className?: string }) {
  return (
    <div
      id={`step-${step.id}`}
      className={cn(
        "relative scroll-mt-24 rounded-lg pl-9 transition-colors duration-700",
        flashing && "bg-amber-100/60 ring-1 ring-amber-400/50 dark:bg-amber-400/10",
        className,
      )}
    >
      {children}
    </div>
  );
}

/** Long content starts clipped. `open` forces it open (a quoted step must show its highlights). */
function Clamp({ children, max, open: forcedOpen }: { children: ReactNode; max: number; open: boolean }) {
  const [open, setOpen] = useState(false);
  const [tall, setTall] = useState(false);
  const inner = useRef<HTMLDivElement | null>(null);
  const expanded = open || forcedOpen;

  useLayoutEffect(() => {
    setTall(inner.current!.scrollHeight > max + 40);
  }, [children, max]);

  return (
    <div>
      <div
        ref={inner}
        style={expanded ? undefined : { maxHeight: max }}
        className={cn("overflow-hidden", !expanded && tall && "[mask-image:linear-gradient(to_bottom,black_75%,transparent)]")}
      >
        {children}
      </div>
      {tall && !forcedOpen && (
        <button
          type="button"
          onClick={() => setOpen(!open)}
          className="mt-1.5 cursor-pointer text-[12px] font-medium text-muted-foreground underline decoration-border underline-offset-4 hover:text-foreground"
        >
          {open ? "Show less" : "Show more"}
        </button>
      )}
    </div>
  );
}

/** + / − / comment for one step. Hidden until hover unless the step already has labels. */
function StepActions({ step, ann }: { step: RmStep; ann: StepAnnotations }) {
  const rating = ann.rating(step);
  const comments = ann.commentCount(step);
  const quiet = rating.positive + rating.negative + comments === 0;
  return (
    <span
      onClick={(e) => e.stopPropagation()}
      className={cn(
        "flex shrink-0 items-center gap-1 transition-opacity",
        quiet && "opacity-0 group-hover/row:opacity-100 focus-within:opacity-100",
      )}
    >
      {isRateable(step) && (
        <>
          <RatingButton rating={1} count={rating.positive} mine={rating.mine === 1} pending={rating.pending === 1} onClick={() => ann.onRate(step, 1)} />
          <RatingButton rating={-1} count={rating.negative} mine={rating.mine === -1} pending={rating.pending === -1} onClick={() => ann.onRate(step, -1)} />
        </>
      )}
      <button
        type="button"
        onClick={(e) => ann.onComment(step, e.currentTarget)}
        title="Comment on this step"
        aria-label="Comment on this step"
        className="inline-flex h-6 cursor-pointer items-center gap-1 rounded-md border border-border bg-background px-1.5 font-mono text-[11px] text-muted-foreground transition-colors hover:border-foreground/20 hover:text-foreground"
      >
        <MessageSquarePlus className="h-3 w-3" />
        {comments > 0 && <span>{comments}</span>}
      </button>
    </span>
  );
}

function RatedBar({ step, ann }: { step: RmStep; ann: StepAnnotations }) {
  const mine = ann.rating(step).mine;
  if (mine === null) return null;
  return (
    <span
      aria-hidden
      className={cn("absolute top-1 bottom-1 -left-0.5 w-[3px] rounded-full", mine === 1 ? "bg-green-600/60" : "bg-red-500/60")}
    />
  );
}

function StepContent({ step, ann, markdown, max }: { step: RmStep; ann: StepAnnotations; markdown: boolean; max: number }) {
  return (
    <Clamp max={max} open={ann.hasQuotes(step)}>
      <AnchoredText
        stepId={step.id}
        content={step.content}
        markdown={markdown}
        highlights={ann.highlights(step)}
        onSelectAnnotation={ann.onSelectAnnotation}
      />
    </Clamp>
  );
}

/* ── user prompt (turn header) ──────────────────────────────────────── */

function PromptRow({ step, turn, ann }: { step: RmStep; turn: number; ann: StepAnnotations }) {
  return (
    <RowFrame step={step} flashing={ann.flashing(step)} className="group/row">
      <Node tone="user">
        <User size={12} />
      </Node>
      <div className="relative rounded-xl border border-amber-200/70 bg-amber-50/60 px-4 py-3 dark:border-amber-400/20 dark:bg-amber-400/5">
        <RatedBar step={step} ann={ann} />
        <div className="mb-1.5 flex items-center gap-3">
          <span className="font-mono text-[11px] tracking-wide text-amber-800 dark:text-amber-300">TURN {turn}</span>
          <span className="text-[12px] font-medium text-dim">User</span>
          <span className="font-mono text-[11px] text-muted-foreground tabular-nums">#{step.index}</span>
          <span className="flex-1" />
          <StepActions step={step} ann={ann} />
        </div>
        <StepContent step={step} ann={ann} markdown max={300} />
      </div>
    </RowFrame>
  );
}

/* ── assistant message (or reasoning) ───────────────────────────────── */

function AssistantRow({ step, ann }: { step: RmStep; ann: StepAnnotations }) {
  const thinking = isThinking(step);
  return (
    <RowFrame step={step} flashing={ann.flashing(step)} className="group/row py-1.5">
      <Node tone={thinking ? "think" : "asst"}>{thinking ? <Brain size={12} /> : <Bot size={12} />}</Node>
      <div className="relative -mx-2 rounded-lg px-2 py-1">
        <RatedBar step={step} ann={ann} />
        <div className="mb-1 flex items-center gap-3">
          <span className="text-[12px] font-medium text-dim">{thinking ? "Thinking" : "Assistant"}</span>
          <span className="font-mono text-[11px] text-muted-foreground tabular-nums">#{step.index}</span>
          <span className="flex-1" />
          <StepActions step={step} ann={ann} />
        </div>
        <div className={cn(thinking && "text-dim italic")}>
          <StepContent step={step} ann={ann} markdown max={440} />
        </div>
      </div>
    </RowFrame>
  );
}

/* ── tool call + result ─────────────────────────────────────────────── */

function ToolRow({
  call,
  result,
  ann,
  expanded,
  onToggle,
}: {
  call: RmStep | null;
  result: RmStep | null;
  ann: StepAnnotations;
  expanded: boolean;
  onToggle: () => void;
}) {
  const head = (call ?? result)!;
  const name = call?.tool_name ?? result!.tool_name;
  const family = toolFamily(name);
  const isError = result !== null && looksLikeError(result.content);
  const summary = call ? toolSummary(call.tool_input) : firstLine(result!.content);

  return (
    <RowFrame step={head} flashing={ann.flashing(head)}>
      <Node tone={isError ? "err" : "tool"}>
        <ToolIcon family={family} />
      </Node>
      {call && call.content !== "" && (
        <div className="group/row relative mb-1 pt-[3px]">
          <StepContent step={call} ann={ann} markdown max={300} />
        </div>
      )}
      <div
        role="button"
        tabIndex={-1}
        onClick={onToggle}
        className="group/row relative -mx-2 flex cursor-pointer items-center gap-2.5 rounded-lg px-2 py-[5px] transition-colors hover:bg-surface/80"
      >
        <RatedBar step={head} ann={ann} />
        <span className="w-[110px] shrink-0 truncate text-[12.5px] font-medium text-dim" title={name ?? undefined}>
          {toolLabel(name)}
        </span>
        <span className="min-w-0 flex-1 truncate font-mono text-[12.25px] text-foreground" title={summary}>
          {summary}
        </span>
        <span className="font-mono text-[11px] text-muted-foreground tabular-nums">#{head.index}</span>
        <StatusDot status={result === null ? "unknown" : isError ? "error" : "ok"} />
        <StepActions step={head} ann={ann} />
        <span className="text-muted-foreground">{expanded ? <ChevronDown size={13} /> : <ChevronRight size={13} />}</span>
      </div>
      {expanded && (
        <div className="mt-1.5 mb-3 space-y-3 rounded-lg border border-border-subtle bg-background p-3.5 text-[13px] animate-in fade-in-0 slide-in-from-top-1">
          <div className="flex flex-wrap items-center gap-x-4 gap-y-1 font-mono text-[11px] text-muted-foreground">
            <span>{name}</span>
            {head.tool_call_id && <span className="truncate">{head.tool_call_id}</span>}
          </div>
          {call && call.tool_input !== null && (
            <Section title="Input" right={<CopyButton text={JSON.stringify(call.tool_input, null, 2)} />}>
              <pre className="m-0 rounded-md border border-border-subtle bg-surface px-3 py-2 font-mono text-[12px] leading-[1.55] break-words whitespace-pre-wrap text-dim">
                {JSON.stringify(call.tool_input, null, 2)}
              </pre>
            </Section>
          )}
          {result && (
            <div id={call ? `step-${result.id}` : undefined} className={cn("group/row rounded-md", call && ann.flashing(result) && "bg-amber-100/60 dark:bg-amber-400/10")}>
              <Section
                title={`Result · #${result.index}`}
                right={
                  <span className="flex items-center gap-1">
                    {call && <StepActions step={result} ann={ann} />}
                    <CopyButton text={result.content} />
                  </span>
                }
              >
                <div className="rounded-md border border-border-subtle bg-surface px-3 py-2">
                  <StepContent step={result} ann={ann} markdown={false} max={320} />
                </div>
              </Section>
            </div>
          )}
          {result === null && <p className="m-0 text-[12px] text-muted-foreground">No result recorded for this call.</p>}
        </div>
      )}
    </RowFrame>
  );
}

function StatusDot({ status }: { status: "ok" | "error" | "unknown" }) {
  return (
    <span
      aria-label={status}
      className={cn(
        "inline-block size-1.5 shrink-0 rounded-full",
        status === "error" ? "bg-red-500" : status === "ok" ? "bg-green-600" : "border border-muted-foreground",
      )}
    />
  );
}

function Section({ title, right, children }: { title: string; right?: ReactNode; children: ReactNode }) {
  return (
    <div>
      <div className="mb-1 flex items-center justify-between gap-2">
        <span className="sys-label">{title}</span>
        {right}
      </div>
      {children}
    </div>
  );
}

function CopyButton({ text }: { text: string }) {
  const [copied, setCopied] = useState(false);
  return (
    <button
      type="button"
      onClick={(e) => {
        e.stopPropagation();
        void navigator.clipboard.writeText(text).then(() => {
          setCopied(true);
          setTimeout(() => setCopied(false), 1200);
        });
      }}
      className="cursor-pointer rounded p-1 text-muted-foreground hover:bg-raised hover:text-foreground"
      aria-label="Copy"
      title="Copy"
    >
      {copied ? <Check size={12} /> : <Copy size={12} />}
    </button>
  );
}

/* ── system prompt ──────────────────────────────────────────────────── */

function SystemRow({ step, ann, expanded, onToggle }: { step: RmStep; ann: StepAnnotations; expanded: boolean; onToggle: () => void }) {
  return (
    <RowFrame step={step} flashing={ann.flashing(step)}>
      <Node tone="sys">
        <Cog size={11} />
      </Node>
      <div
        role="button"
        tabIndex={-1}
        onClick={onToggle}
        className="group/row -mx-2 flex cursor-pointer items-center gap-2.5 rounded-lg px-2 py-[5px] hover:bg-surface/80"
      >
        <span className="w-[110px] shrink-0 truncate text-[12.5px] font-medium text-muted-foreground">System</span>
        <span className="min-w-0 flex-1 truncate font-mono text-[12px] text-muted-foreground">{firstLine(step.content)}</span>
        <span className="font-mono text-[11px] text-muted-foreground tabular-nums">#{step.index}</span>
        <StepActions step={step} ann={ann} />
        <span className="text-muted-foreground">{expanded ? <ChevronDown size={13} /> : <ChevronRight size={13} />}</span>
      </div>
      {expanded && (
        <div className="mt-1.5 mb-3 space-y-2 rounded-lg border border-border-subtle bg-background p-3.5 animate-in fade-in-0 slide-in-from-top-1">
          <StepContent step={step} ann={ann} markdown={false} max={420} />
          <p className="m-0 text-[11.5px] text-muted-foreground">System prompts aren&apos;t rated — the reward model judges behavior.</p>
        </div>
      )}
    </RowFrame>
  );
}

/* ── timeline ───────────────────────────────────────────────────────── */

export default function TraceTimeline({
  rows,
  ann,
  isExpanded,
  onToggle,
}: {
  rows: TraceRow[];
  ann: StepAnnotations;
  isExpanded: (row: TraceRow) => boolean;
  onToggle: (row: TraceRow) => void;
}) {
  return (
    <div className="relative">
      <span aria-hidden className="absolute top-2 bottom-2 left-[10.5px] w-px bg-border" />
      <div className="space-y-1.5">
        {rows.map((row) => {
          if (row.kind === "system") {
            return <SystemRow key={row.key} step={row.step} ann={ann} expanded={isExpanded(row)} onToggle={() => onToggle(row)} />;
          }
          if (row.kind === "prompt") {
            return (
              <div key={row.key} className={cn(row.turn > 1 && "pt-4")}>
                <PromptRow step={row.step} turn={row.turn} ann={ann} />
              </div>
            );
          }
          if (row.kind === "assistant") return <AssistantRow key={row.key} step={row.step} ann={ann} />;
          return <ToolRow key={row.key} call={row.call} result={row.result} ann={ann} expanded={isExpanded(row)} onToggle={() => onToggle(row)} />;
        })}
      </div>
    </div>
  );
}
