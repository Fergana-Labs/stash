// Design from Priyadarshan's trace viewer (projects/trace_viewer)
"use client";

import { useLayoutEffect, useRef, useState, type ReactNode } from "react";
import { cn } from "@/lib/utils";
import type { RmStep } from "@/lib/types";
import AnchoredText from "./AnchoredText";
import { firstLine, isThinking, looksLikeError, toolLabel, toolSummary, type TraceRow } from "./trace-rows";
import type { Highlight } from "./source-anchors";
import styles from "./TraceMarkdown.module.css";

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
        "relative scroll-mt-44 transition-colors duration-700",
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
        "flex shrink-0 items-center gap-1",
        quiet && "opacity-0 group-hover/row:opacity-100 focus-within:opacity-100",
      )}
    >
      <button
        type="button"
        onClick={() => ann.onComment(step)}
        title="Comment on this step"
        aria-label="Comment on this step"
        className="inline-flex h-5 cursor-pointer items-center gap-1 text-[11px] font-medium text-dim hover:text-foreground hover:underline underline-offset-4"
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

function StepMetadata({ step, ann, children }: { step: RmStep; ann: StepAnnotations; children?: ReactNode }) {
  return (
    <div className="ml-auto flex shrink-0 items-center gap-3 text-[11px] text-muted-foreground tabular-nums">
      <StepTime step={step} />
      <span>Step {step.index + 1}</span>
      <div className="flex w-28 items-center justify-end gap-3">
        <StepActions step={step} ann={ann} />
        {children}
      </div>
    </div>
  );
}

function PromptRow({ step, ann, repeated, expanded, onToggle }: {
  step: RmStep; ann: StepAnnotations; repeated: boolean; expanded: boolean; onToggle: () => void;
}) {
  return (
    <RowFrame step={step} flashing={ann.flashing(step)} className="group/row">
      <div className="mb-1 flex min-h-5 items-center gap-3">
        {repeated ? (
          <button type="button" onClick={onToggle} aria-expanded={expanded}
            className="cursor-pointer text-[11px] text-muted-foreground hover:text-foreground hover:underline underline-offset-4">
            Repeated user message{expanded ? " — hide" : " — show"}
          </button>
        ) : <span className="text-[13px] font-semibold text-foreground">User</span>}
        <StepMetadata step={step} ann={ann} />
      </div>
      {(!repeated || expanded) && <StepContent step={step} ann={ann} markdown max={300} />}
    </RowFrame>
  );
}

/* ── assistant message (or reasoning) ───────────────────────────────── */

function AssistantRow({ step, ann, first }: { step: RmStep; ann: StepAnnotations; first: boolean }) {
  const thinking = isThinking(step);
  return (
    <RowFrame step={step} flashing={ann.flashing(step)} className={cn("group/row", !first && "pt-3")}>
      <div className="mb-1 flex min-h-5 items-center gap-3">
        <span className={cn(first ? "text-[13px] font-semibold text-foreground" : "text-[11px] text-muted-foreground")}>
          {first ? "Assistant" : thinking ? "Thinking" : "Response"}
        </span>
        <StepMetadata step={step} ann={ann} />
      </div>
      <div className={cn(thinking && "text-dim italic")}>
        <StepContent step={step} ann={ann} markdown max={440} />
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
  const summary = call ? toolSummary(call.tool_input)
    : /^\s*[\[{]/.test(result!.content) ? "" : firstLine(result!.content);

  return (
    <RowFrame step={head} flashing={ann.flashing(head)} className="group/row ml-2 border-l border-border pl-3">
      {call && call.content !== "" && (
        <div className="group/row relative mb-1 pt-[3px]">
          <StepContent step={call} ann={ann} markdown max={300} />
        </div>
      )}
      <div className="flex min-h-8 items-center gap-3">
        <button type="button" onClick={onToggle} aria-expanded={expanded}
          aria-label={`${expanded ? "Collapse" : "Expand"} ${toolLabel(name)} ${call ? "tool call" : "tool result"}`}
          className="flex min-w-0 flex-1 cursor-pointer items-center gap-2 text-left hover:text-foreground">
          <span className="max-w-44 shrink-0 truncate text-[12px] font-medium text-foreground" title={name ?? undefined}>{toolLabel(name)}</span>
          <span className="shrink-0 text-[10px] text-muted-foreground">{call ? "Tool call" : "Tool result"}</span>
          <span className="min-w-0 truncate text-[12px] text-muted-foreground" title={summary}>{expanded ? "" : summary}</span>
        </button>
        {isError && <span className="text-[11px] text-red-600">Error</span>}
        <StepMetadata step={head} ann={ann}>
          <button type="button" onClick={onToggle} aria-expanded={expanded}
            className="shrink-0 cursor-pointer text-[11px] font-medium text-dim hover:text-foreground hover:underline underline-offset-4">
            {expanded ? "Hide" : "Details"}
          </button>
        </StepMetadata>
      </div>
      {expanded && (
        <div className={cn("mb-1 grid gap-3 text-[13px]", call?.tool_input != null && result !== null && "grid-cols-2")}>
          {call && call.tool_input !== null && (
            <Section title="Input" right={<CopyButton text={JSON.stringify(call.tool_input, null, 2)} />}>
              <pre className={cn(styles.out, "m-0 bg-surface/60 px-3 py-2")}>
                {JSON.stringify(call.tool_input, null, 2)}
              </pre>
            </Section>
          )}
          {result && (
            <div id={call ? `step-${result.id}` : undefined} className={cn("group/row", call && ann.flashing(result) && "bg-amber-100/60 dark:bg-amber-400/10")}>
              <Section
                title="Result"
                right={
                  <span className="flex items-center gap-3">
                    {call && <StepTime step={result} />}
                    {call && <span className="text-[11px] text-muted-foreground">Step {result.index + 1}</span>}
                    {call && <StepActions step={result} ann={ann} />}
                    <CopyButton text={result.content} />
                  </span>
                }
              >
                <div className="bg-surface/60 px-3 py-2">
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
        <span className="text-[11px] font-medium text-muted-foreground">{title}</span>
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
      className="cursor-pointer text-[11px] font-medium text-dim hover:text-foreground hover:underline underline-offset-4"
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
      <div className="group/row flex min-h-7 items-center gap-3">
        <button type="button" onClick={onToggle} aria-expanded={expanded} aria-label={`${expanded ? "Collapse" : "Expand"} system prompt`}
          className="flex min-w-0 flex-1 cursor-pointer items-center gap-2 text-left text-[12px] text-muted-foreground hover:text-foreground">
          <span className="shrink-0 font-medium">System</span>
          <span className="truncate">{expanded ? "" : firstLine(step.content)}</span>
        </button>
        <StepMetadata step={step} ann={ann}>
          <button type="button" onClick={onToggle} aria-expanded={expanded}
            className="cursor-pointer text-[11px] font-medium text-dim hover:text-foreground hover:underline underline-offset-4">
            {expanded ? "Hide" : "Details"}
          </button>
        </StepMetadata>
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
    if (last && last.assistant === assistant) last.rows.push(row);
    else groups.push({ assistant, rows: [row] });
  }

  function renderRow(row: TraceRow, index: number, groupRows: TraceRow[]) {
    if (row.kind === "system") {
      return <SystemRow key={row.key} step={row.step} ann={ann} expanded={isExpanded(row)} onToggle={() => onToggle(row)} />;
    }
    if (row.kind === "prompt") {
      const previous = groupRows[index - 1];
      const repeated = previous?.kind === "prompt" && previous.step.index + 1 === row.step.index
        && previous.step.content === row.step.content;
      return <PromptRow key={row.key} step={row.step} ann={ann} repeated={repeated}
        expanded={isExpanded(row)} onToggle={() => onToggle(row)} />;
    }
    if (row.kind === "assistant") return <AssistantRow key={row.key} step={row.step} ann={ann} first={index === 0} />;
    return <ToolRow key={row.key} call={row.call} result={row.result} ann={ann} expanded={isExpanded(row)} onToggle={() => onToggle(row)} />;
  }

  return (
    <div className="divide-y divide-border-subtle">
      {groups.map((group) => (
        <section key={group.rows[0].key} aria-label={group.assistant ? "Assistant turn" : "Conversation messages"} className="py-3">
          {group.assistant && group.rows[0].kind === "tool" && <h3 className="m-0 mb-1 text-[13px] font-semibold text-foreground">Assistant</h3>}
          <div className={cn(!group.assistant && "space-y-2")}>{group.rows.map((row, index) => renderRow(row, index, group.rows))}</div>
        </section>
      ))}
    </div>
  );
}
