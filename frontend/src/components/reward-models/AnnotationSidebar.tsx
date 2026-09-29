"use client";

import { useState } from "react";
import { Flag, FlagOff, Loader2, Trash2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import type { RmAnnotation, RmStep } from "@/lib/types";
import { RatingPill } from "./rm-ui";
import { relativeTime } from "./rm-text";

export default function AnnotationSidebar({
  annotations,
  steps,
  viewerId,
  activeId,
  pendingId,
  onSelect,
  onFlag,
  onUnflag,
  onDelete,
}: {
  /** Already in document order. */
  annotations: RmAnnotation[];
  steps: RmStep[];
  viewerId: string;
  activeId: string | null;
  /** The annotation with a request in flight, if any. */
  pendingId: string | null;
  onSelect: (annotation: RmAnnotation) => void;
  onFlag: (annotation: RmAnnotation, note: string) => void;
  onUnflag: (annotation: RmAnnotation) => void;
  onDelete: (annotation: RmAnnotation) => void;
}) {
  const stepById = new Map(steps.map((s) => [s.id, s]));
  const flagged = annotations.filter((a) => a.label_error).length;

  return (
    <aside className="scroll-thin flex w-[360px] shrink-0 flex-col overflow-y-auto border-l border-border bg-surface/50">
      <div className="sticky top-0 z-10 flex items-baseline justify-between border-b border-border bg-surface/95 px-4 py-3 backdrop-blur">
        <span className="sys-label">Annotations</span>
        <span className="text-[11.5px] text-muted-foreground tabular-nums">
          {annotations.length}
          {flagged > 0 && ` · ${flagged} flagged`}
        </span>
      </div>
      {annotations.length === 0 ? (
        <p className="m-0 px-4 py-6 text-[12.5px] leading-relaxed text-muted-foreground">
          Rate a step with + or −, or select text in any step to comment on it. Everything you add shows up here.
        </p>
      ) : (
        <div className="flex flex-col gap-2 p-3">
          {annotations.map((annotation) => (
            <AnnotationCard
              key={annotation.id}
              annotation={annotation}
              target={annotation.step_id === null ? null : stepById.get(annotation.step_id)!}
              mine={annotation.author_id === viewerId}
              active={annotation.id === activeId}
              pending={annotation.id === pendingId}
              onSelect={() => onSelect(annotation)}
              onFlag={(note) => onFlag(annotation, note)}
              onUnflag={() => onUnflag(annotation)}
              onDelete={() => onDelete(annotation)}
            />
          ))}
        </div>
      )}
    </aside>
  );
}

function AnnotationCard({
  annotation,
  target,
  mine,
  active,
  pending,
  onSelect,
  onFlag,
  onUnflag,
  onDelete,
}: {
  annotation: RmAnnotation;
  /** The step this annotation is on; null = the whole trace. */
  target: RmStep | null;
  mine: boolean;
  active: boolean;
  pending: boolean;
  onSelect: () => void;
  onFlag: (note: string) => void;
  onUnflag: () => void;
  onDelete: () => void;
}) {
  const [flagging, setFlagging] = useState(false);
  const [note, setNote] = useState("");
  const flagged = annotation.label_error;

  return (
    <div
      id={`annotation-${annotation.id}`}
      onClick={onSelect}
      className={cn(
        "group/card cursor-pointer rounded-lg border bg-background px-3 py-2.5 text-[12.5px] transition-shadow",
        active ? "border-amber-400/70 shadow-sm ring-2 ring-amber-400/20" : "border-border hover:shadow-sm",
      )}
    >
      <div className="flex items-center gap-1.5">
        <span className="truncate font-medium text-foreground">{annotation.author_name}</span>
        <span className="shrink-0 text-[11px] text-muted-foreground">{relativeTime(annotation.created_at)}</span>
        <span className="flex-1" />
        <div
          className={cn(
            "flex items-center transition-opacity",
            !active && !pending && "opacity-0 group-hover/card:opacity-100 focus-within:opacity-100",
          )}
          onClick={(e) => e.stopPropagation()}
        >
          {pending && <Loader2 className="mr-1 h-3.5 w-3.5 animate-spin text-muted-foreground" />}
          {flagged ? (
            <Button variant="ghost" size="icon-xs" disabled={pending} onClick={onUnflag} title="Unflag: include this label again" aria-label="Unflag label error" className="text-muted-foreground">
              <FlagOff />
            </Button>
          ) : (
            <Button
              variant="ghost"
              size="icon-xs"
              disabled={pending || flagging}
              onClick={() => setFlagging(true)}
              title="Reward model label error: exclude this label from training"
              aria-label="Flag reward model label error"
              className="text-muted-foreground hover:text-amber-700"
            >
              <Flag />
            </Button>
          )}
          {mine && (
            <Button
              variant="ghost"
              size="icon-xs"
              disabled={pending}
              onClick={onDelete}
              aria-label="Delete annotation"
              title="Delete"
              className="text-muted-foreground hover:text-red-600"
            >
              <Trash2 />
            </Button>
          )}
        </div>
        <span className="shrink-0 font-mono text-[10.5px] tracking-wide text-muted-foreground uppercase">
          {target === null ? "Trace" : `Step ${target.index} · ${target.role}`}
        </span>
      </div>

      <div className={cn("mt-1.5 flex flex-col gap-1.5", flagged && "opacity-55")}>
        {annotation.rating !== null && (
          <div className={cn(flagged && "line-through")}>
            <RatingPill rating={annotation.rating} />
          </div>
        )}
        {annotation.quote && (
          <div className="line-clamp-3 border-l-2 border-amber-400/80 pl-2 leading-snug text-dim italic">
            {annotation.quote.text}
          </div>
        )}
        {annotation.comment && (
          <div className={cn("leading-snug whitespace-pre-wrap text-foreground", flagged && "line-through decoration-foreground/40")}>
            {annotation.comment}
          </div>
        )}
      </div>

      {flagged && (
        <div className="mt-2 flex gap-1.5 rounded-md bg-amber-500/10 px-2 py-1.5 text-[12px] text-amber-800 dark:text-amber-300">
          <Flag className="mt-0.5 h-3 w-3 shrink-0" />
          <div>
            <span className="font-medium">Label error</span>
            {annotation.label_error_note && <span> — {annotation.label_error_note}</span>}
            <div className="text-[11px] opacity-80">Excluded from training and skill creation.</div>
          </div>
        </div>
      )}

      {flagging && (
        <div className="mt-2 flex flex-col gap-1.5" onClick={(e) => e.stopPropagation()}>
          <input
            autoFocus
            value={note}
            onChange={(e) => setNote(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter") {
                onFlag(note.trim());
                setFlagging(false);
              }
              if (e.key === "Escape") setFlagging(false);
            }}
            placeholder="Why is this label wrong? (optional)"
            className="h-7 w-full rounded-md border border-border bg-background px-2 text-[12px] outline-none focus:border-amber-500 focus:ring-2 focus:ring-amber-500/20"
          />
          <div className="flex justify-end gap-1">
            <Button variant="ghost" size="xs" onClick={() => setFlagging(false)}>
              Cancel
            </Button>
            <Button
              size="xs"
              className="bg-amber-600 text-white hover:bg-amber-600/85"
              onClick={() => {
                onFlag(note.trim());
                setFlagging(false);
              }}
            >
              Flag label error
            </Button>
          </div>
        </div>
      )}
    </div>
  );
}
