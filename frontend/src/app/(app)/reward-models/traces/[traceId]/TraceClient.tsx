"use client";

import Link from "next/link";
import { useCallback, useEffect, useRef, useState, type MouseEvent } from "react";
import { ArrowLeft, MessageSquarePlus } from "lucide-react";
import { toast } from "sonner";
import { useBreadcrumbs } from "@/components/BreadcrumbContext";
import { useConfirm } from "@/components/ConfirmDialog";
import AnnotationComposer, { COMPOSER_WIDTH, type ComposerTarget } from "@/components/reward-models/AnnotationComposer";
import AnnotationSidebar from "@/components/reward-models/AnnotationSidebar";
import { TraceSkeleton } from "@/components/reward-models/RmSkeletons";
import TraceStep, { isRateable, type StepRatingState } from "@/components/reward-models/TraceStep";
import { RatingButton } from "@/components/reward-models/rm-ui";
import { errorMessage, formatScore, quoteFromOffsets, relativeTime, sortAnnotations } from "@/components/reward-models/rm-text";
import { useAuth } from "@/hooks/useAuth";
import { rmCreateAnnotation, rmDeleteAnnotation, rmGetTrace, rmUpdateAnnotation } from "@/lib/api";
import type { RmAnnotation, RmQuote, RmTraceDetail } from "@/lib/types";

const FLASH_MS = 1400;

/** A rating given with the + / − buttons: no comment, no quote. The buttons toggle exactly this annotation. */
function isPlainRating(a: RmAnnotation): boolean {
  return a.rating !== null && a.comment === null && a.quote === null;
}

/** Character offset of (node, offset) counted from the start of `root`'s text. */
function textOffset(root: Node, node: Node, offset: number): number {
  const range = document.createRange();
  range.selectNodeContents(root);
  range.setEnd(node, offset);
  return range.toString().length;
}

function stepContentElement(node: Node | null): HTMLElement | null {
  const element = node instanceof HTMLElement ? node : node?.parentElement;
  return element?.closest<HTMLElement>("[data-step-content]") ?? null;
}

export default function TraceClient({ traceId }: { traceId: string }) {
  const { user } = useAuth();
  const confirm = useConfirm();
  const [trace, setTrace] = useState<RmTraceDetail | null>(null);
  const [composer, setComposer] = useState<ComposerTarget | null>(null);
  const [activeId, setActiveId] = useState<string | null>(null);
  const [flashStepId, setFlashStepId] = useState<string | null>(null);
  // Which rating button is waiting on the server: "<stepId|trace>:<rating>".
  const [pendingRating, setPendingRating] = useState<string | null>(null);
  const [pendingAnnotationId, setPendingAnnotationId] = useState<string | null>(null);
  const canvas = useRef<HTMLDivElement | null>(null);

  useBreadcrumbs(
    [{ label: "Reward models", href: "/reward-models" }, { label: trace?.title ?? "Trace" }],
    `rm-trace-${traceId}-${trace?.title ?? ""}`,
  );

  const load = useCallback(async () => {
    try {
      setTrace(await rmGetTrace(traceId));
    } catch (e) {
      toast.error(errorMessage(e));
    }
  }, [traceId]);

  useEffect(() => {
    void load();
  }, [load]);

  useEffect(() => {
    if (flashStepId === null) return;
    const timer = setTimeout(() => setFlashStepId(null), FLASH_MS);
    return () => clearTimeout(timer);
  }, [flashStepId]);

  const closeComposer = useCallback(() => setComposer(null), []);

  if (!trace || !user) return <TraceSkeleton />;
  const viewerId = user.id;
  const ordered = sortAnnotations(trace.annotations, trace.steps);

  function ratingState(stepId: string | null): StepRatingState {
    const live = trace!.annotations.filter((a) => a.step_id === stepId && !a.label_error);
    const mine = live.find((a) => a.author_id === viewerId && isPlainRating(a));
    const [key, value] = (pendingRating ?? ":").split(":");
    return {
      positive: live.filter((a) => a.rating === 1).length,
      negative: live.filter((a) => a.rating === -1).length,
      mine: mine ? mine.rating : null,
      pending: key === (stepId ?? "trace") ? (Number(value) as 1 | -1) : null,
    };
  }

  async function rate(stepId: string | null, rating: 1 | -1) {
    const mine = trace!.annotations.find(
      (a) => a.step_id === stepId && a.author_id === viewerId && isPlainRating(a) && !a.label_error,
    );
    setPendingRating(`${stepId ?? "trace"}:${rating}`);
    try {
      if (mine && mine.rating === rating) await rmDeleteAnnotation(mine.id);
      else if (mine) await rmUpdateAnnotation(mine.id, { rating });
      else await rmCreateAnnotation(traceId, stepId === null ? { rating } : { step_id: stepId, rating });
      await load();
    } catch (e) {
      toast.error(errorMessage(e));
    } finally {
      setPendingRating(null);
    }
  }

  async function submitComment(target: ComposerTarget, comment: string, rating: 1 | -1 | null) {
    try {
      await rmCreateAnnotation(traceId, {
        ...(target.stepId !== null && { step_id: target.stepId }),
        ...(target.quote !== null && { quote: target.quote }),
        ...(comment !== "" && { comment }),
        ...(rating !== null && { rating }),
      });
      await load();
      setComposer(null);
      window.getSelection()?.removeAllRanges();
    } catch (e) {
      toast.error(errorMessage(e));
    }
  }

  async function mutateAnnotation(annotation: RmAnnotation, run: () => Promise<unknown>) {
    setPendingAnnotationId(annotation.id);
    try {
      await run();
      await load();
    } catch (e) {
      toast.error(errorMessage(e));
    } finally {
      setPendingAnnotationId(null);
    }
  }

  async function deleteAnnotation(annotation: RmAnnotation) {
    const ok = await confirm({ title: "Delete this annotation?", confirmLabel: "Delete" });
    if (!ok) return;
    await mutateAnnotation(annotation, () => rmDeleteAnnotation(annotation.id));
  }

  /** Composer position just under `rect`, kept inside the canvas. */
  function positionUnder(rect: DOMRect, alignLeft: number): { top: number; left: number } {
    const box = canvas.current!.getBoundingClientRect();
    const maxLeft = box.width - COMPOSER_WIDTH - 8;
    return {
      top: rect.bottom - box.top + 8,
      left: Math.max(8, Math.min(alignLeft - box.left, maxLeft)),
    };
  }

  function openComposerAt(anchor: HTMLElement, stepId: string | null) {
    const rect = anchor.getBoundingClientRect();
    setComposer({ stepId, quote: null, ...positionUnder(rect, rect.right - COMPOSER_WIDTH) });
  }

  // Text selected inside one step's content opens the composer on that span.
  function onCanvasMouseUp(e: MouseEvent) {
    if ((e.target as HTMLElement).closest("button, input, textarea")) return;
    const selection = window.getSelection();
    if (!selection || selection.isCollapsed || selection.rangeCount === 0) return;
    const contentEl = stepContentElement(selection.anchorNode);
    if (!contentEl || contentEl !== stepContentElement(selection.focusNode)) return;

    const stepId = contentEl.dataset.stepContent!;
    const step = trace!.steps.find((s) => s.id === stepId)!;
    const range = selection.getRangeAt(0);
    const start = textOffset(contentEl, range.startContainer, range.startOffset);
    const end = textOffset(contentEl, range.endContainer, range.endOffset);
    if (step.content.slice(start, end).trim() === "") return;

    const quote: RmQuote = quoteFromOffsets(step.content, start, end);
    const rect = range.getBoundingClientRect();
    setComposer({ stepId, quote, ...positionUnder(rect, rect.left) });
  }

  function focusAnnotation(annotation: RmAnnotation) {
    setActiveId(annotation.id);
    if (annotation.step_id === null) {
      canvas.current!.scrollIntoView({ behavior: "smooth", block: "start" });
      return;
    }
    document.getElementById(`step-${annotation.step_id}`)?.scrollIntoView({ behavior: "smooth", block: "center" });
    setFlashStepId(annotation.step_id);
  }

  function focusCard(id: string) {
    setActiveId(id);
    document.getElementById(`annotation-${id}`)?.scrollIntoView({ behavior: "smooth", block: "nearest" });
  }

  const traceRating = ratingState(null);
  const traceComments = trace.annotations.filter((a) => a.step_id === null && a.comment !== null).length;

  return (
    <div className="flex h-full min-h-0">
      <div className="scroll-thin min-w-0 flex-1 overflow-y-auto">
        <div ref={canvas} className="relative mx-auto max-w-4xl px-8 pt-6 pb-24" onMouseUp={onCanvasMouseUp}>
          <Link
            href="/reward-models"
            className="inline-flex items-center gap-1 text-[12px] text-muted-foreground hover:text-foreground"
          >
            <ArrowLeft className="h-3.5 w-3.5" />
            Traces
          </Link>

          <header className="mt-3 mb-6 border-b border-border pb-5">
            <div className="flex items-start gap-4">
              <div className="min-w-0 flex-1">
                <h1 className="m-0 font-display text-[21px] leading-snug font-semibold tracking-tight text-foreground">
                  {trace.title}
                </h1>
                <div className="mt-1.5 flex flex-wrap items-center gap-2 text-[12px] text-muted-foreground">
                  <span className="tag tag-muted">{trace.source_format}</span>
                  <span>{trace.step_count} steps</span>
                  {trace.external_id && <span className="font-mono">{trace.external_id}</span>}
                  <span>imported {relativeTime(trace.created_at)}</span>
                </div>
              </div>
              <div className="flex shrink-0 items-center gap-1.5 pt-1">
                <span className="mr-1 text-[11.5px] text-muted-foreground">Whole trace</span>
                <RatingButton size="md" rating={1} count={traceRating.positive} mine={traceRating.mine === 1} pending={traceRating.pending === 1} onClick={() => void rate(null, 1)} />
                <RatingButton size="md" rating={-1} count={traceRating.negative} mine={traceRating.mine === -1} pending={traceRating.pending === -1} onClick={() => void rate(null, -1)} />
                <button
                  type="button"
                  onClick={(e) => openComposerAt(e.currentTarget, null)}
                  className="inline-flex h-7 cursor-pointer items-center gap-1 rounded-md border border-border bg-background px-2 text-[12px] text-muted-foreground transition-colors hover:border-foreground/20 hover:text-foreground"
                >
                  <MessageSquarePlus className="h-3.5 w-3.5" />
                  Comment{traceComments > 0 && ` · ${traceComments}`}
                </button>
              </div>
            </div>

            {trace.scores.length > 0 && (
              <div className="mt-4 flex flex-wrap gap-2">
                {trace.scores.map((s) => (
                  <div
                    key={s.reward_model_id}
                    title={`Scored ${relativeTime(s.created_at)}`}
                    className="flex items-baseline gap-2 rounded-md border border-border bg-surface/60 px-2.5 py-1"
                  >
                    <span className="text-[11.5px] text-muted-foreground">{s.reward_model_name}</span>
                    <span className="font-mono text-[13px] font-medium text-foreground tabular-nums">{formatScore(s.score)}</span>
                  </div>
                ))}
              </div>
            )}
          </header>

          <p className="m-0 mb-3 text-[11.5px] text-muted-foreground">
            Select text in any step to comment on it. + / − rate the whole step.
          </p>

          <div className="flex flex-col gap-1">
            {trace.steps.map((step) => (
              <TraceStep
                key={step.id}
                step={step}
                annotations={trace.annotations.filter((a) => a.step_id === step.id)}
                pendingQuote={composer?.stepId === step.id ? composer.quote : null}
                activeId={activeId}
                flashing={flashStepId === step.id}
                rating={ratingState(step.id)}
                onRate={(rating) => void rate(step.id, rating)}
                onComment={(anchor) => openComposerAt(anchor, step.id)}
                onSelectAnnotation={focusCard}
              />
            ))}
          </div>

          {composer && (
            <AnnotationComposer
              key={`${composer.stepId}-${composer.top}-${composer.left}`}
              target={composer}
              label={composerLabel(composer, trace)}
              allowRating={composer.stepId === null || isRateable(trace.steps.find((s) => s.id === composer.stepId)!)}
              onCancel={closeComposer}
              onSubmit={(comment, rating) => submitComment(composer, comment, rating)}
            />
          )}
        </div>
      </div>

      <AnnotationSidebar
        annotations={ordered}
        steps={trace.steps}
        viewerId={viewerId}
        activeId={activeId}
        pendingId={pendingAnnotationId}
        onSelect={focusAnnotation}
        onFlag={(a, note) =>
          void mutateAnnotation(a, () =>
            rmUpdateAnnotation(a.id, note === "" ? { label_error: true } : { label_error: true, label_error_note: note }),
          )
        }
        onUnflag={(a) => void mutateAnnotation(a, () => rmUpdateAnnotation(a.id, { label_error: false }))}
        onDelete={(a) => void deleteAnnotation(a)}
      />
    </div>
  );
}

function composerLabel(target: ComposerTarget, trace: RmTraceDetail): string {
  if (target.stepId === null) return "Comment on the whole trace";
  const step = trace.steps.find((s) => s.id === target.stepId)!;
  return target.quote ? `Comment on selection · step ${step.index}` : `Comment on step ${step.index} · ${step.role}`;
}
