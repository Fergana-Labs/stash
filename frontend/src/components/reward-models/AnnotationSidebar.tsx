// Aside layout from Priyadarshan's trace viewer (projects/trace_viewer)
"use client";

import { useState, type ReactNode } from "react";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import type { RmAnnotation, RmStep } from "@/lib/types";
import { relativeTime } from "./rm-text";

export default function AnnotationSidebar({
  visible,
  onClose,
  onAddComment,
  annotations,
  steps,
  viewerId,
  activeId,
  pendingId,
  onSelect,
  onFlag,
  onUnflag,
  onDelete,
  composer,
}: {
  visible: boolean;
  onClose: () => void;
  onAddComment: () => void;
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
  composer: ReactNode;
}) {
  const stepById = new Map(steps.map((s) => [s.id, s]));
  const flagged = annotations.filter((a) => a.label_error).length;

  return (
    <aside aria-label="Trace comments" className={cn("scroll-thin flex w-[360px] shrink-0 flex-col gap-4 overflow-y-auto border-l border-border bg-surface/50 p-4", !visible && "hidden")}>
      <div className="flex justify-end"><Button variant="ghost" size="xs" onClick={onClose}>Close comments</Button></div>
      <section id="trace-comments">
        <div className="flex items-baseline justify-between px-3 pt-2 pb-3">
          <h3 className="sys-label m-0">Comments</h3>
          <span className="font-mono text-[11px] text-muted-foreground tabular-nums">
            {annotations.length}
            {flagged > 0 && `, ${flagged} flagged`}
          </span>
        </div>
        {!composer && <Button variant="ghost" size="sm" className="mb-2 ml-1" onClick={onAddComment}>Add comment</Button>}
        {composer && <div className="mx-3 mb-1 border-b border-border pb-4">{composer}</div>}
        {annotations.length === 0 ? (
          <p className="m-0 px-3 pb-4 text-[12.5px] leading-relaxed text-muted-foreground">
            Select text or use Comment on any step. Your comments appear here.
          </p>
        ) : (
          <div className="flex flex-col divide-y divide-border">
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
      </section>
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
        "group/card cursor-pointer border-l-2 px-3 py-3 text-[12.5px] transition-colors",
        active ? "border-l-amber-400 bg-amber-400/5" : "border-l-transparent hover:bg-background/60",
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
          {pending && <span>Saving…</span>}
          {flagged ? (
            <Button variant="ghost" size="xs" disabled={pending} onClick={onUnflag} title="Unflag: include this label again" aria-label="Unflag label error" className="text-muted-foreground">
              Unflag
            </Button>
          ) : (
            <Button
              variant="ghost"
              size="xs"
              disabled={pending || flagging}
              onClick={() => setFlagging(true)}
              title="Reward model label error: exclude this label from training"
              aria-label="Flag reward model label error"
              className="text-muted-foreground hover:text-amber-700"
            >
              Flag
            </Button>
          )}
          {mine && (
            <Button
              variant="ghost"
              size="xs"
              disabled={pending}
              onClick={onDelete}
              aria-label="Delete annotation"
              title="Delete"
              className="text-muted-foreground hover:text-red-600"
            >
              Delete
            </Button>
          )}
        </div>
        <span className="shrink-0 font-mono text-[10.5px] tracking-wide text-muted-foreground uppercase">
          {target === null ? "Trace" : `Step ${target.index + 1} (${target.role})`}
        </span>
      </div>

      <div className={cn("mt-1.5 flex flex-col gap-1.5", flagged && "opacity-55")}>
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
