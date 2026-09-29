"use client";

import { useState } from "react";
import { ChevronDown, CornerDownRight, MessageSquarePlus } from "lucide-react";
import { cn } from "@/lib/utils";
import type { RmAnnotation, RmQuote, RmRole, RmStep } from "@/lib/types";
import { RatingButton } from "./rm-ui";
import { buildSegments, locateQuote, type Segment } from "./rm-text";

/** Highlight id for the not-yet-saved quote while the composer is open. */
export const PENDING_ID = "pending";

const ROLE_TAG: Record<RmRole, string> = {
  system: "tag-muted",
  user: "tag-human",
  assistant: "tag-agent",
  tool: "bg-violet-500/12 text-violet-700 dark:text-violet-300",
};

// Long tool results start clipped. The full text stays in the DOM so text
// selection offsets always match the stored content.
const COLLAPSE_CHARS = 700;

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

export default function TraceStep({
  step,
  annotations,
  pendingQuote,
  activeId,
  flashing,
  rating,
  onRate,
  onComment,
  onSelectAnnotation,
}: {
  step: RmStep;
  /** Every annotation attached to this step. */
  annotations: RmAnnotation[];
  pendingQuote: RmQuote | null;
  activeId: string | null;
  flashing: boolean;
  rating: StepRatingState;
  onRate: (rating: 1 | -1) => void;
  onComment: (anchor: HTMLElement) => void;
  onSelectAnnotation: (id: string) => void;
}) {
  const quoted = annotations.filter((a) => a.quote !== null);
  const commentCount = annotations.filter((a) => a.comment !== null).length;
  const collapsible = step.role === "tool" && step.content.length > COLLAPSE_CHARS;
  const [expanded, setExpanded] = useState(quoted.length > 0);
  const isToolCall = step.role === "assistant" && step.tool_name !== null;
  const rateable = isRateable(step);

  return (
    <div
      id={`step-${step.id}`}
      className={cn(
        "group/step relative rounded-lg border px-4 py-3 transition-colors duration-700",
        flashing
          ? "border-amber-400/60 bg-amber-100/50 dark:bg-amber-400/10"
          : "border-transparent hover:border-border hover:bg-surface/40",
      )}
    >
      {rating.mine !== null && (
        <span
          aria-hidden
          className={cn(
            "absolute top-3 bottom-3 left-0 w-[3px] rounded-full",
            rating.mine === 1 ? "bg-green-600/60" : "bg-red-500/60",
          )}
        />
      )}
      <div className="mb-1.5 flex items-center gap-2">
        <span className="w-6 font-mono text-[11px] text-muted-foreground/70 tabular-nums">{step.index}</span>
        <span className={cn("tag", ROLE_TAG[step.role])}>{step.role}</span>
        {step.role === "tool" && step.tool_name && (
          <span className="font-mono text-[11.5px] text-dim">{step.tool_name}</span>
        )}
        {step.tool_call_id && (
          <span className="truncate font-mono text-[10.5px] text-muted-foreground/70">{step.tool_call_id}</span>
        )}
        <span className="flex-1" />
        <div
          className={cn(
            "flex items-center gap-1 transition-opacity",
            rating.positive + rating.negative + commentCount === 0 && "opacity-0 group-hover/step:opacity-100 focus-within:opacity-100",
          )}
        >
          {rateable && (
            <>
              <RatingButton rating={1} count={rating.positive} mine={rating.mine === 1} pending={rating.pending === 1} onClick={() => onRate(1)} />
              <RatingButton rating={-1} count={rating.negative} mine={rating.mine === -1} pending={rating.pending === -1} onClick={() => onRate(-1)} />
            </>
          )}
          <button
            type="button"
            onClick={(e) => onComment(e.currentTarget)}
            title="Comment on this step"
            aria-label="Comment on this step"
            className="inline-flex h-6 cursor-pointer items-center gap-1 rounded-md border border-border bg-background px-1.5 font-mono text-[11px] text-muted-foreground transition-colors hover:border-foreground/20 hover:text-foreground"
          >
            <MessageSquarePlus className="h-3 w-3" />
            {commentCount > 0 && <span>{commentCount}</span>}
          </button>
        </div>
      </div>

      <div className="pl-8">
        {step.content !== "" && (
          <div className={cn("relative", collapsible && !expanded && "max-h-40 overflow-hidden")}>
            <div
              data-step-content={step.id}
              className={cn(
                "text-[13.5px] leading-[1.65] break-words whitespace-pre-wrap text-foreground",
                (step.role === "tool" || step.role === "system") && "font-mono text-[12.5px] leading-relaxed text-dim",
              )}
            >
              <HighlightedContent
                content={step.content}
                annotations={quoted}
                pendingQuote={pendingQuote}
                activeId={activeId}
                onSelectAnnotation={onSelectAnnotation}
              />
            </div>
            {collapsible && !expanded && (
              <div className="pointer-events-none absolute inset-x-0 bottom-0 h-14 bg-gradient-to-t from-background to-transparent" />
            )}
          </div>
        )}
        {collapsible && (
          <button
            type="button"
            onClick={() => setExpanded(!expanded)}
            className="mt-1 inline-flex cursor-pointer items-center gap-1 text-[12px] text-muted-foreground hover:text-foreground"
          >
            <ChevronDown className={cn("h-3.5 w-3.5 transition-transform", expanded && "rotate-180")} />
            {expanded ? "Collapse result" : `Show full result (${step.content.split("\n").length} lines)`}
          </button>
        )}
        {!rateable && (
          <p className="m-0 mt-1.5 text-[11.5px] text-muted-foreground">
            System prompts aren&apos;t rated — the reward model judges behavior.
          </p>
        )}
        {isToolCall && <ToolCall name={step.tool_name!} input={step.tool_input} />}
      </div>
    </div>
  );
}

function ToolCall({ name, input }: { name: string; input: Record<string, unknown> | null }) {
  return (
    <div className="mt-2 overflow-hidden rounded-md border border-border bg-surface/60">
      <div className="flex items-center gap-1.5 border-b border-border-subtle px-2.5 py-1.5 font-mono text-[12px] text-foreground">
        <CornerDownRight className="h-3.5 w-3.5 text-brand-500" />
        {name}
      </div>
      {input !== null && (
        <pre className="scroll-thin m-0 max-h-72 overflow-auto px-2.5 py-2 font-mono text-[12px] leading-relaxed text-dim">
          {JSON.stringify(input, null, 2)}
        </pre>
      )}
    </div>
  );
}

function HighlightedContent({
  content,
  annotations,
  pendingQuote,
  activeId,
  onSelectAnnotation,
}: {
  content: string;
  annotations: RmAnnotation[];
  pendingQuote: RmQuote | null;
  activeId: string | null;
  onSelectAnnotation: (id: string) => void;
}) {
  const byId = new Map(annotations.map((a) => [a.id, a]));
  const highlights = annotations.flatMap((a) => {
    const range = locateQuote(content, a.quote!);
    return range ? [{ id: a.id, ...range }] : [];
  });
  if (pendingQuote) {
    const range = locateQuote(content, pendingQuote);
    if (range) highlights.push({ id: PENDING_ID, ...range });
  }

  return (
    <>
      {buildSegments(content, highlights).map((segment, i) =>
        segment.ids.length === 0 ? (
          segment.text
        ) : (
          <mark
            key={i}
            onClick={() => {
              const saved = segment.ids.find((id) => id !== PENDING_ID);
              if (saved) onSelectAnnotation(saved);
            }}
            className={cn(
              "cursor-pointer rounded-[2px] text-inherit transition-colors",
              markStyle(segment, byId),
              activeId !== null && segment.ids.includes(activeId) && "ring-1 ring-amber-500/70 brightness-95",
            )}
          >
            {segment.text}
          </mark>
        ),
      )}
    </>
  );
}

function markStyle(segment: Segment, byId: Map<string, RmAnnotation>): string {
  if (segment.ids.includes(PENDING_ID)) return "bg-brand-300/45";
  const live = segment.ids.map((id) => byId.get(id)!).filter((a) => !a.label_error);
  if (live.length === 0) return "bg-transparent underline decoration-muted-foreground/50 decoration-dashed underline-offset-4";
  if (live.some((a) => a.rating === -1)) return "bg-red-500/15 underline decoration-red-500/60 underline-offset-4";
  if (live.some((a) => a.rating === 1)) return "bg-green-500/15 underline decoration-green-600/60 underline-offset-4";
  return "bg-yellow-200/60 dark:bg-yellow-400/25";
}
