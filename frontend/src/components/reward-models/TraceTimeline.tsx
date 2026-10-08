// Design from Priyadarshan's trace viewer (projects/trace_viewer)
"use client";

import { useLayoutEffect, useRef, useState, type ReactNode } from "react";
import { toast } from "sonner";
import { cn } from "@/lib/utils";
import type { RmActionScore, RmStep } from "@/lib/types";
import { creditColor, formatCredit } from "./action-credit";
import { StepLabelChips } from "./StepLabels";
import { StepScoreChip, StepScoreLine, TaskScoreChip } from "./StepRewards";
import type { LabelChip } from "./step-labels";
import { signed, type StepReward, type TaskScore } from "./step-rewards";
import AnchoredText from "./AnchoredText";
import { firstLine, isThinking, looksLikeError, toolLabel, toolSummary, type TraceRow } from "./trace-rows";
import type { Highlight } from "./source-anchors";
import { Check, Copy, ChevronDown, ChevronRight } from "lucide-react";
import { readableExcerpt } from "./trace-presentation";
import ToolInput from "./ToolInput";

/** Everything a row needs to show and change one step's annotations. Built once per render by the trace page. */
export interface StepAnnotations {
  stepNumber?: (step: RmStep) => number | undefined;
  /** A reward model's score for the step, for views that have no step scores. */
  actionScore?: (step: RmStep) => RmActionScore | undefined;
  /** Step labels (what each step is); absent when the trace has none or they are hidden. */
  labelChips?: (step: RmStep) => LabelChip[];
  taskHeading?: (step: RmStep) => string | null;
  onJumpToStep?: (stepId: string) => void;
  /** Each step's score and how it was built; absent unless scores are shown. */
  reward?: (step: RmStep) => StepReward | null;
  /** The score of the task a step belongs to, shown where the task starts. */
  taskScore?: (step: RmStep) => TaskScore | null;
  stepNumberOf?: (chunk: string) => number | null;
  onJumpToChunk?: (chunk: string) => void;
  highlights: (step: RmStep) => Highlight[];
  commentCount: (step: RmStep) => number;
  hasQuotes: (step: RmStep) => boolean;
  flashing: (step: RmStep) => boolean;
  onComment: (step: RmStep) => void;
  onSelectAnnotation: (ids: string[]) => void;
}

function Labels({ step, ann, className }: { step: RmStep; ann: StepAnnotations; className?: string }) {
  const chips = ann.labelChips?.(step) ?? [];
  if (chips.length === 0 || !ann.onJumpToStep) return null;
  return <StepLabelChips chips={chips} onJump={ann.onJumpToStep} className={className} />;
}

/** The breakdown is the deepest level of detail, so it only appears once a row is opened. */
function ScoreLine({ step, ann, className }: { step: RmStep; ann: StepAnnotations; className?: string }) {
  const reward = ann.reward?.(step);
  if (!reward || !ann.stepNumberOf || !ann.onJumpToChunk) return null;
  return <StepScoreLine reward={reward} stepNumberOf={ann.stepNumberOf} onJumpToChunk={ann.onJumpToChunk} className={className} />;
}

/** The id is the scroll target for the minimap and comments. */
function RowFrame({ step, ann, children, className }: { step: RmStep; ann: StepAnnotations; children: ReactNode; className?: string }) {
  return (
    <div
      id={`step-${step.id}`}
      className={cn(
        "relative scroll-mt-44 transition-colors duration-700",
        "pr-2 pl-8",
        ann.flashing(step) && "bg-amber-100/60 ring-1 ring-amber-400/50 dark:bg-amber-400/10",
        className,
      )}
    >
      <span aria-label={`Step ${ann.stepNumber?.(step) ?? step.index + 1}`} className="absolute top-1 left-0 w-6 text-right font-mono text-[10px] tabular-nums text-muted-foreground">{ann.stepNumber?.(step) ?? step.index + 1}</span>
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
    const measure = () => setTall(inner.current!.scrollHeight > max + 40);
    measure();
    const observer = new ResizeObserver(measure);
    if (inner.current?.firstElementChild) observer.observe(inner.current.firstElementChild);
    return () => observer.disconnect();
  }, [children, max]);

  return (
    <div onKeyDown={(event) => { if (event.key === "Escape" && open) { event.stopPropagation(); event.preventDefault(); setOpen(false); } }}>
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
          aria-expanded={expanded}
          onClick={() => setOpen(!open)}
          className="mt-1.5 cursor-pointer text-[12px] font-medium text-muted-foreground underline decoration-border underline-offset-4 hover:text-foreground"
        >
          {open ? "Show less" : "Read full message"}
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
        "flex shrink-0 items-center gap-2",
        quiet && "opacity-0 group-hover/row:opacity-100 focus-within:opacity-100",
      )}
    >
      <button
        type="button"
        onClick={() => ann.onComment(step)}
        title="Comment on this step"
        aria-label="Comment on this step"
        className={cn("inline-flex h-5 cursor-pointer items-center gap-1 text-[11px] font-medium text-dim hover:text-foreground hover:underline underline-offset-4", comments === 0 && "opacity-0 group-hover/row:opacity-100 focus:opacity-100")}
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
    <Clamp max={Math.min(max, 160)} open={ann.hasQuotes(step)}>
      <AnchoredText
        stepId={step.id}
        content={step.content}
        images={step.images}
        markdown={markdown}
        highlights={ann.highlights(step)}
        onSelectAnnotation={ann.onSelectAnnotation}
      />
    </Clamp>
  );
}

/* ── user prompt (turn header) ──────────────────────────────────────── */

function StepMetadata({ step, ann }: { step: RmStep; ann: StepAnnotations }) {
  const reward = ann.reward?.(step);
  const score = reward ? undefined : ann.actionScore?.(step);
  return (
    <div className="ml-auto flex shrink-0 items-center gap-3 text-[11px] text-muted-foreground tabular-nums">
      <span className="text-right"><StepTime step={step} /></span>
      {reward ? <span className="flex justify-end"><StepScoreChip reward={reward} /></span> : (
        <span className="text-right">{score && <span className="font-mono" style={{ color: creditColor(score.credit) }}
        aria-label={`Action credit ${formatCredit(score.credit)}${score.stale ? ", previous annotation" : ""}`}
        title={`${score.stale ? "Previous automatic annotation" : "Automatic action annotation"}: ${formatCredit(score.credit)} (−1 to +1). Estimated contribution to the task; not a judgment of the message type.`}>
        {formatCredit(score.credit)}{score.stale && <span className="ml-0.5 text-muted-foreground" aria-hidden="true">*</span>}
      </span>}</span>
      )}
      <span className="flex justify-end"><StepActions step={step} ann={ann} /></span>
    </div>
  );
}

function DisclosureIcon({ expanded }: { expanded: boolean }) {
  const Icon = expanded ? ChevronDown : ChevronRight;
  return <Icon className="size-3.5 shrink-0 text-muted-foreground" aria-hidden="true" />;
}

function PromptRow({ step, ann, repeated, expanded, onToggle }: {
  step: RmStep; ann: StepAnnotations; repeated: boolean; expanded: boolean; onToggle: () => void;
}) {
  return (
    <RowFrame step={step} ann={ann} className="group/row">
      <div className="mb-2 flex min-h-8 items-center gap-3">
        <button type="button" onClick={onToggle} aria-expanded={expanded}
          aria-label={`${expanded ? "Collapse" : "Expand"} ${repeated ? "repeated user message" : "user message"}`}
          className="flex min-w-0 flex-1 cursor-pointer items-center gap-2 text-left">
          <DisclosureIcon expanded={expanded} />
          <span className="shrink-0 text-[13px] font-semibold text-amber-700 dark:text-amber-300">{repeated ? "Repeated user message" : "User"}</span>
          {!expanded && !repeated && <span className="truncate text-xs text-muted-foreground">{readableExcerpt(step.content)}</span>}
        </button>
        <Labels step={step} ann={ann} className="shrink-0 flex-nowrap" />
        <StepMetadata step={step} ann={ann} />
      </div>
      {expanded && <StepContent step={step} ann={ann} markdown max={300} />}
    </RowFrame>
  );
}

/* ── assistant message (or reasoning) ───────────────────────────────── */

function AssistantRow({ step, ann, first }: { step: RmStep; ann: StepAnnotations; first: boolean }) {
  const thinking = isThinking(step);
  return (
    <RowFrame step={step} ann={ann} className={cn("group/row", !first && "pt-3")}>
      <div className="mb-1 flex min-h-5 items-center gap-3">
        <span className={cn(first ? "text-[13px] font-semibold text-blue-600 dark:text-blue-300" : "text-[11px] text-blue-600 dark:text-blue-300")}>
          {first ? "Assistant" : thinking ? "Thinking" : "Response"}
        </span>
        <Labels step={step} ann={ann} />
        <StepMetadata step={step} ann={ann} />
      </div>
      <ScoreLine step={step} ann={ann} className="mb-1.5" />
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
    <RowFrame step={head} ann={ann} className="group/row">
      {call && call.content !== "" && (
        <div className="group/row relative mb-1 pt-[3px]">
          <StepContent step={call} ann={ann} markdown max={300} />
        </div>
      )}
      <div className="flex min-h-8 items-center gap-3">
        <button type="button" onClick={onToggle} aria-expanded={expanded}
          aria-label={`${expanded ? "Collapse" : "Expand"} ${toolLabel(name)} ${call ? "tool call" : "tool result"}`}
          className="flex min-w-0 flex-1 cursor-pointer items-center gap-2 text-left hover:text-foreground">
          <DisclosureIcon expanded={expanded} />
          <span className="max-w-44 shrink-0 truncate text-[13px] font-medium text-violet-700 dark:text-violet-300" title={name ?? undefined}>{toolLabel(name)}</span>

          <span className="min-w-0 truncate text-[12px] text-muted-foreground" title={summary}>{expanded ? "" : summary}</span>
        </button>
        {isError && <span className="text-[11px] text-red-600">Error</span>}
        <Labels step={head} ann={ann} className="shrink-0 flex-nowrap" />
        <StepMetadata step={head} ann={ann} />
      </div>
      {expanded && <ScoreLine step={head} ann={ann} className="mb-2 ml-5" />}
      {expanded && <div className="mb-2 ml-5 text-[13px]">
        {call?.tool_input && <ToolInput input={call.tool_input} tool={name ?? ""} />}
        {result && <ToolOutput step={result} ann={ann} nested={call !== null} />}
      </div>}
    </RowFrame>
  );
}

function ToolOutput({ step, ann, nested }: { step: RmStep; ann: StepAnnotations; nested: boolean }) {
  const [open, setOpen] = useState(false);
  const expanded = open || ann.hasQuotes(step);
  const [copied, setCopied] = useState(false);
  return <div id={nested ? `step-${step.id}` : undefined} className="group/output border-t border-border-subtle">
    <div className="flex min-h-7 items-center gap-2">
      <button type="button" onClick={() => setOpen(!open)} aria-expanded={expanded} aria-label={`${expanded ? "Collapse" : "Expand"} tool output`} className="flex min-w-0 flex-1 cursor-pointer items-center gap-2 text-left text-xs">
        <DisclosureIcon expanded={expanded} /><span className="font-medium text-teal-700 dark:text-teal-300">Output</span>
        {!expanded && <span className="truncate font-mono text-muted-foreground">{firstLine(step.content)}</span>}
      </button>
      <button type="button" aria-label="Copy tool output" title="Copy tool output" onClick={() => void navigator.clipboard.writeText(step.content).then(() => { setCopied(true); setTimeout(() => setCopied(false), 1200); }).catch(() => toast.error("Couldn’t copy this output."))} className="cursor-pointer p-1 text-muted-foreground opacity-0 group-hover/output:opacity-100 focus:opacity-100">{copied ? <Check className="size-3" /> : <Copy className="size-3" />}</button>
    </div>
    {expanded && <div className="mb-2 rounded-md bg-surface/60 px-3 py-2"><AnchoredText stepId={step.id} content={step.content} images={step.images} markdown={false} highlights={ann.highlights(step)} onSelectAnnotation={ann.onSelectAnnotation} /></div>}
  </div>;
}

/* ── recorded system message ──────────────────────────────────────────────────── */

function SystemRow({ step, ann, expanded, onToggle }: { step: RmStep; ann: StepAnnotations; expanded: boolean; onToggle: () => void }) {
  return (
    <RowFrame step={step} ann={ann}>
      <div className="group/row flex min-h-8 items-center gap-3">
        <button type="button" onClick={onToggle} aria-expanded={expanded} aria-label={`${expanded ? "Collapse" : "Expand"} system message`}
          className="flex min-w-0 flex-1 cursor-pointer items-center gap-2 text-left text-[12px] text-muted-foreground hover:text-foreground">
          <DisclosureIcon expanded={expanded} /><span className="shrink-0 font-medium">System</span>
          {!expanded && <span className="truncate text-xs">{readableExcerpt(step.content)}</span>}
        </button>
        <StepMetadata step={step} ann={ann} />
      </div>
      {expanded && <div className="mb-4 mt-2 pl-5"><StepContent step={step} ann={ann} markdown max={420} /></div>}
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
      const task = ann.taskHeading?.(row.step) ?? null;
      const taskScore = task === null ? null : ann.taskScore?.(row.step) ?? null;
      return (
        <div key={row.key}>
          {task !== null && (
            <div className="mb-2 flex items-center gap-2 text-[10.5px] font-medium tracking-wide text-muted-foreground uppercase">
              <span>{task}</span>
              {taskScore && <TaskScoreChip score={taskScore} />}
              {taskScore && (
                <span className="font-normal tracking-normal normal-case">
                  {taskScore.hasAnswer ? "final answer" : "no answer"} {signed(taskScore.answer ?? 0)} · work {signed(taskScore.costs)}
                </span>
              )}
              <span aria-hidden="true" className="h-px flex-1 bg-border-subtle" />
            </div>
          )}
          <PromptRow step={row.step} ann={ann} repeated={repeated} expanded={isExpanded(row)} onToggle={() => onToggle(row)} />
        </div>
      );
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
