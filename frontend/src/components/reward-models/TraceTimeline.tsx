// Design from Priyadarshan's trace viewer (projects/trace_viewer)
"use client";

import { useLayoutEffect, useRef, useState, type ReactNode } from "react";
import { cn } from "@/lib/utils";
import type { RmStep } from "@/lib/types";
import AnchoredText from "./AnchoredText";
import { firstLine, isThinking, looksLikeError, toolLabel, toolSummary, type TraceRow } from "./trace-rows";
import type { Highlight } from "./source-anchors";

/** Everything a row needs to show and change one step's annotations. Built once per render by the trace page. */
export interface StepAnnotations {
  highlights: (step: RmStep) => Highlight[];
  commentCount: (step: RmStep) => number;
  hasQuotes: (step: RmStep) => boolean;
  flashing: (step: RmStep) => boolean;
  onComment: (step: RmStep) => void;
  onSelectAnnotation: (ids: string[]) => void;
}

/** The id is the scroll target for the minimap and comments. */
function RowFrame({ step, flashing, children, className }: { step: RmStep; flashing: boolean; children: ReactNode; className?: string }) {
  return (
    <div
      id={`step-${step.id}`}
      className={cn(
        "relative scroll-mt-44 border-b border-border-subtle py-1 transition-colors duration-700",
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

/** Keep empty comment controls quiet until the row is focused or hovered. */
function StepActions({ step, ann }: { step: RmStep; ann: StepAnnotations }) {
  const comments = ann.commentCount(step);
  const quiet = comments === 0;
  return (
    <span
      onClick={(e) => e.stopPropagation()}
      className={cn(
        "flex shrink-0 items-center gap-1 transition-opacity",
        quiet && "opacity-0 group-hover/row:opacity-100 focus-within:opacity-100",
      )}
    >
      <button
        type="button"
        onClick={() => ann.onComment(step)}
        title="Comment on this step"
        aria-label="Comment on this step"
        className="inline-flex h-6 cursor-pointer items-center gap-1 rounded-md border border-border bg-background px-1.5 font-mono text-[11px] text-muted-foreground transition-colors hover:border-foreground/20 hover:text-foreground"
      >
        Comment{comments > 0 && ` (${comments})`}
      </button>
    </span>
  );
}

function StepTime({ step }: { step: RmStep }) {
  const timestamp = step.metadata?.timestamp;
  if (typeof timestamp !== "string") return null;
  const time = new Date(timestamp);
  return (
    <time dateTime={timestamp} title={time.toLocaleString()} className="shrink-0 text-[11px] text-muted-foreground tabular-nums">
      {time.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" })}
    </time>
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

function PromptRow({ step, ann }: { step: RmStep; ann: StepAnnotations }) {
  return (
    <RowFrame step={step} flashing={ann.flashing(step)} className="group/row">
      <div className="relative py-1.5">
        <div className="mb-0.5 flex items-center gap-2">
          <span className="text-[12px] font-medium text-dim">User</span>
          <span className="font-mono text-[11px] text-muted-foreground tabular-nums">Step {step.index + 1}</span>
          <StepTime step={step} />
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
    <RowFrame step={step} flashing={ann.flashing(step)} className="group/row py-0.5">
      <div className="relative -mx-2 px-2 py-1">
        <div className="mb-1 flex items-center gap-3">
          <span className="text-[12px] font-medium text-dim">{thinking ? "Thinking" : "Response"}</span>
          <span className="font-mono text-[11px] text-muted-foreground tabular-nums">Step {step.index + 1}</span>
          <StepTime step={step} />
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
  const isError = result !== null && looksLikeError(result.content);
  const summary = call ? toolSummary(call.tool_input) : firstLine(result!.content);

  return (
    <RowFrame step={head} flashing={ann.flashing(head)} className="ml-4 border-l border-border pl-3">
      {call && call.content !== "" && (
        <div className="group/row relative mb-1 pt-[3px]">
          <StepContent step={call} ann={ann} markdown max={300} />
        </div>
      )}
      <div
        role="button"
        tabIndex={-1}
        onClick={onToggle}
        className="group/row relative -mx-2 flex cursor-pointer items-center gap-2.5 px-2 py-[5px] transition-colors hover:bg-surface/80"
      >
        <span className="shrink-0 text-[10.5px] text-muted-foreground">{call ? "Tool call" : "Tool result"}</span>
        <span className="max-w-[140px] shrink-0 truncate text-[12.5px] font-medium text-dim" title={name ?? undefined}>
          {toolLabel(name)}
        </span>
        <span className="min-w-0 flex-1 truncate font-mono text-[12.25px] text-foreground" title={summary}>
          {summary}
        </span>
        <span className="font-mono text-[11px] text-muted-foreground tabular-nums">Step {head.index + 1}</span>
        <StepTime step={head} />
        {isError && <span className="text-[11px] text-red-600">Error</span>}
        <StepActions step={head} ann={ann} />
        <span className="text-[11px] text-muted-foreground">{expanded ? "Hide" : "Show"}</span>
      </div>
      {expanded && (
        <div className="mb-1 grid grid-cols-2 gap-3 text-[13px]">
          {call && call.tool_input !== null && (
            <Section title="Input" right={<CopyButton text={JSON.stringify(call.tool_input)} />}>
              <pre className="m-0 bg-surface/60 px-2 py-1 font-mono text-[12px] leading-[1.4] break-words whitespace-pre-wrap text-dim">
                {JSON.stringify(call.tool_input)}
              </pre>
            </Section>
          )}
          {result && (
            <div id={call ? `step-${result.id}` : undefined} className={cn("group/row", call && ann.flashing(result) && "bg-amber-100/60 dark:bg-amber-400/10")}>
              <Section
                title={`Result (Step ${result.index + 1})`}
                right={
                  <span className="flex items-center gap-1">
                    <StepTime step={result} />
                    {call && <StepActions step={result} ann={ann} />}
                    <CopyButton text={result.content} />
                  </span>
                }
              >
                <div className="bg-surface/60 px-2 py-1">
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

function Section({ title, right, children }: { title: string; right?: ReactNode; children: ReactNode }) {
  return (
    <div>
      <div className="mb-1 flex h-6 items-center justify-between gap-2">
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
      className="cursor-pointer rounded px-1 text-[11px] text-muted-foreground hover:bg-raised hover:text-foreground"
      aria-label="Copy"
      title="Copy"
    >
      {copied ? "Copied" : "Copy"}
    </button>
  );
}

/* ── system prompt ──────────────────────────────────────────────────── */

function SystemRow({ step, ann, expanded, onToggle }: { step: RmStep; ann: StepAnnotations; expanded: boolean; onToggle: () => void }) {
  return (
    <RowFrame step={step} flashing={ann.flashing(step)}>
      <div
        role="button"
        tabIndex={-1}
        onClick={onToggle}
        className="group/row -mx-2 flex cursor-pointer items-center gap-2.5 px-2 py-[5px] hover:bg-surface/80"
      >
        <span className="w-[110px] shrink-0 truncate text-[12.5px] font-medium text-muted-foreground">System</span>
        <span className="min-w-0 flex-1 truncate font-mono text-[12px] text-muted-foreground">{expanded ? "" : firstLine(step.content)}</span>
        <span className="font-mono text-[11px] text-muted-foreground tabular-nums">Step {step.index + 1}</span>
        <StepTime step={step} />
        <StepActions step={step} ann={ann} />
        <span className="text-[11px] text-muted-foreground">{expanded ? "Hide" : "Show"}</span>
      </div>
      {expanded && (
        <div className="mb-1 pl-3">
          <StepContent step={step} ann={ann} markdown={false} max={420} />
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
  const groups: { assistant: boolean; rows: TraceRow[] }[] = [];
  for (const row of rows) {
    const assistant = row.kind === "tool" || row.kind === "assistant";
    const last = groups.at(-1);
    if (assistant && last?.assistant) last.rows.push(row);
    else groups.push({ assistant, rows: [row] });
  }

  function renderRow(row: TraceRow) {
    if (row.kind === "system") {
      return <SystemRow key={row.key} step={row.step} ann={ann} expanded={isExpanded(row)} onToggle={() => onToggle(row)} />;
    }
    if (row.kind === "prompt") return <PromptRow key={row.key} step={row.step} ann={ann} />;
    if (row.kind === "assistant") return <AssistantRow key={row.key} step={row.step} ann={ann} />;
    return <ToolRow key={row.key} call={row.call} result={row.result} ann={ann} expanded={isExpanded(row)} onToggle={() => onToggle(row)} />;
  }

  return (
    <div className="space-y-2">
      {groups.map((group) => group.assistant ? (
        <section key={group.rows[0].key} aria-label="Assistant turn">
          <h3 className="m-0 mb-1 text-[12px] font-medium text-dim">Assistant</h3>
          <div className="space-y-1">{group.rows.map(renderRow)}</div>
        </section>
      ) : <div key={group.rows[0].key}>{group.rows.map(renderRow)}</div>)}
    </div>
  );
}
