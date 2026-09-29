"use client";

import Link from "next/link";
import { useCallback, useEffect, useRef, useState, type MouseEvent, type ReactNode } from "react";
import { ArrowLeft, ChevronsDownUp, ChevronsUpDown, MessageSquarePlus } from "lucide-react";
import { toast } from "sonner";
import { useBreadcrumbs } from "@/components/BreadcrumbContext";
import { useConfirm } from "@/components/ConfirmDialog";
import AnnotationComposer, { COMPOSER_WIDTH, type ComposerTarget } from "@/components/reward-models/AnnotationComposer";
import AnnotationSidebar from "@/components/reward-models/AnnotationSidebar";
import { TraceSkeleton } from "@/components/reward-models/RmSkeletons";
import TraceMinimap, { MinimapLegend } from "@/components/reward-models/TraceMinimap";
import TraceOverview from "@/components/reward-models/TraceOverview";
import TraceTimeline, { isRateable, type StepAnnotations, type StepRatingState } from "@/components/reward-models/TraceTimeline";
import { RatingButton } from "@/components/reward-models/rm-ui";
import { errorMessage, locateQuote, quoteFromOffsets, relativeTime, sortAnnotations } from "@/components/reward-models/rm-text";
import { domSourceOffset, type Highlight } from "@/components/reward-models/source-anchors";
import { buildRows, rowSteps, type TraceRow } from "@/components/reward-models/trace-rows";
import { useAuth } from "@/hooks/useAuth";
import { rmCreateAnnotation, rmDeleteAnnotation, rmGetTrace, rmUpdateAnnotation } from "@/lib/api";
import { cn } from "@/lib/utils";
import type { RmAnnotation, RmStep, RmTraceDetail } from "@/lib/types";

const FLASH_MS = 1400;
/** Highlight id for the not-yet-saved quote while the composer is open. */
const PENDING_ID = "pending";
// The step whose row crosses this line (px below the scroll container's top) is the minimap cursor.
const CURSOR_LINE_PX = 80;

type View = "all" | "conversation" | "tools";

const VIEWS: [View, string][] = [
  ["all", "All"],
  ["conversation", "Conversation"],
  ["tools", "Tools"],
];

/** A rating given with the + / − buttons: no comment, no quote. The buttons toggle exactly this annotation. */
function isPlainRating(a: RmAnnotation): boolean {
  return a.rating !== null && a.comment === null && a.quote === null;
}

function stepContentElement(node: Node | null): HTMLElement | null {
  const element = node instanceof HTMLElement ? node : node?.parentElement;
  return element?.closest<HTMLElement>("[data-step-content]") ?? null;
}

// Where two highlights overlap, the first one's color shows: pending, then −, then +, then comments, then flagged.
function highlightRank(a: RmAnnotation): number {
  if (a.label_error) return 4;
  if (a.rating === -1) return 1;
  if (a.rating === 1) return 2;
  return 3;
}

function highlightClass(a: RmAnnotation, active: boolean): string {
  return cn(
    "cursor-pointer rounded-[2px] text-inherit transition-colors",
    a.label_error
      ? "bg-transparent underline decoration-muted-foreground/50 decoration-dashed underline-offset-4"
      : a.rating === -1
        ? "bg-red-500/15 underline decoration-red-500/60 underline-offset-4"
        : a.rating === 1
          ? "bg-green-500/15 underline decoration-green-600/60 underline-offset-4"
          : "bg-yellow-200/60 dark:bg-yellow-400/25",
    active && "ring-1 ring-amber-500/70 brightness-95",
  );
}

function inView(row: TraceRow, view: View): boolean {
  if (view === "all") return true;
  if (view === "tools") return row.kind === "tool";
  return row.kind === "prompt" || row.kind === "assistant";
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
  const [view, setView] = useState<View>("all");
  const [expandAll, setExpandAll] = useState(false);
  // Rows the user opened (true) or closed (false) by hand; the rest follow their default.
  const [rowChoice, setRowChoice] = useState<Map<string, boolean>>(new Map());
  const [cursorStepId, setCursorStepId] = useState<string | null>(null);
  const canvas = useRef<HTMLDivElement | null>(null);
  const scroller = useRef<HTMLDivElement | null>(null);

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

  // Minimap cursor: the first step whose row reaches past the cursor line.
  const steps = trace?.steps ?? null;
  useEffect(() => {
    const container = scroller.current;
    if (!container || steps === null) return;
    let frame = 0;
    function update() {
      const top = container!.getBoundingClientRect().top + CURSOR_LINE_PX;
      const current = steps!.find((s) => {
        const el = document.getElementById(`step-${s.id}`);
        return el !== null && el.getBoundingClientRect().bottom > top;
      });
      setCursorStepId(current ? current.id : null);
    }
    function onScroll() {
      cancelAnimationFrame(frame);
      frame = requestAnimationFrame(update);
    }
    update();
    container.addEventListener("scroll", onScroll, { passive: true });
    return () => {
      container.removeEventListener("scroll", onScroll);
      cancelAnimationFrame(frame);
    };
  }, [steps]);

  const closeComposer = useCallback(() => setComposer(null), []);

  if (!trace || !user) return <TraceSkeleton />;
  const viewerId = user.id;
  const ordered = sortAnnotations(trace.annotations, trace.steps);
  const rows = buildRows(trace.steps);
  const displaySteps = rows.flatMap(rowSteps);

  function annotationsOn(step: RmStep): RmAnnotation[] {
    return trace!.annotations.filter((a) => a.step_id === step.id);
  }

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

  function highlightsFor(step: RmStep): Highlight[] {
    const saved = annotationsOn(step)
      .filter((a) => a.quote !== null)
      .sort((a, b) => highlightRank(a) - highlightRank(b))
      .flatMap((a) => {
        const range = locateQuote(step.content, a.quote!);
        return range ? [{ id: a.id, ...range, className: highlightClass(a, a.id === activeId) }] : [];
      });
    if (composer?.stepId !== step.id || composer.quote === null) return saved;
    const pending = locateQuote(step.content, composer.quote);
    if (pending === null) return saved;
    return [{ id: PENDING_ID, ...pending, className: "rounded-[2px] bg-brand-300/45 text-inherit" }, ...saved];
  }

  /** Rows with annotations start open so their highlights and labels are visible. */
  function isExpanded(row: TraceRow): boolean {
    const choice = rowChoice.get(row.key);
    if (choice !== undefined) return choice;
    return expandAll || rowSteps(row).some((s) => annotationsOn(s).length > 0);
  }

  function toggleRow(row: TraceRow) {
    setRowChoice(new Map(rowChoice).set(row.key, !isExpanded(row)));
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
  // Offsets come from the rendered runs' source offsets, so a quote made on
  // rendered markdown is stored against the raw step content.
  function onCanvasMouseUp(e: MouseEvent) {
    if ((e.target as HTMLElement).closest("button, input, textarea")) return;
    const selection = window.getSelection();
    if (!selection || selection.isCollapsed || selection.rangeCount === 0) return;
    const contentEl = stepContentElement(selection.anchorNode);
    if (!contentEl || contentEl !== stepContentElement(selection.focusNode)) return;

    const step = trace!.steps.find((s) => s.id === contentEl.dataset.stepContent)!;
    const range = selection.getRangeAt(0);
    const start = domSourceOffset(range.startContainer, range.startOffset);
    const end = domSourceOffset(range.endContainer, range.endOffset);
    if (start === null || end === null) {
      toast.error("That selection starts or ends on formatted text that can't be quoted. Select plain words.");
      return;
    }
    if (end <= start || step.content.slice(start, end).trim() === "") return;

    const rect = range.getBoundingClientRect();
    setComposer({ stepId: step.id, quote: quoteFromOffsets(step.content, start, end), ...positionUnder(rect, rect.left) });
  }

  /** Scrolls to a step, opening its row and clearing a filter that hides it. */
  function revealStep(stepId: string) {
    const row = rows.find((r) => rowSteps(r).some((s) => s.id === stepId))!;
    if (!inView(row, view)) setView("all");
    if (!isExpanded(row) && (row.kind === "tool" || row.kind === "system")) toggleRow(row);
    setFlashStepId(stepId);
    requestAnimationFrame(() =>
      document.getElementById(`step-${stepId}`)?.scrollIntoView({ behavior: "smooth", block: "center" }),
    );
  }

  function focusAnnotation(annotation: RmAnnotation) {
    setActiveId(annotation.id);
    if (annotation.step_id === null) {
      canvas.current!.scrollIntoView({ behavior: "smooth", block: "start" });
      return;
    }
    revealStep(annotation.step_id);
  }

  function focusCard(ids: string[]) {
    const id = ids.find((i) => i !== PENDING_ID);
    if (id === undefined) return;
    setActiveId(id);
    document.getElementById(`annotation-${id}`)?.scrollIntoView({ behavior: "smooth", block: "nearest" });
  }

  const ann: StepAnnotations = {
    highlights: highlightsFor,
    rating: (step) => ratingState(step.id),
    commentCount: (step) => annotationsOn(step).filter((a) => a.comment !== null).length,
    hasQuotes: (step) => annotationsOn(step).some((a) => a.quote !== null) || composer?.stepId === step.id,
    flashing: (step) => flashStepId === step.id,
    onRate: (step, rating) => void rate(step.id, rating),
    onComment: (step, anchor) => openComposerAt(anchor, step.id),
    onSelectAnnotation: focusCard,
  };

  const traceRating = ratingState(null);
  const traceComments = trace.annotations.filter((a) => a.step_id === null && a.comment !== null).length;
  const visibleRows = rows.filter((row) => inView(row, view));
  const cursorIndex = displaySteps.findIndex((s) => s.id === cursorStepId);

  return (
    <div className="flex h-full min-h-0">
      <div ref={scroller} className="scroll-thin min-w-0 flex-1 overflow-y-auto">
        <div ref={canvas} className="relative mx-auto max-w-4xl px-8 pt-6 pb-24" onMouseUp={onCanvasMouseUp}>
          <Link href="/reward-models" className="inline-flex items-center gap-1 text-[12px] text-muted-foreground hover:text-foreground">
            <ArrowLeft className="h-3.5 w-3.5" />
            Traces
          </Link>

          <header className="mt-3 mb-5 flex items-start gap-4">
            <div className="min-w-0 flex-1">
              <h1 className="m-0 font-display text-[21px] leading-snug font-semibold tracking-tight text-foreground">{trace.title}</h1>
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
          </header>

          <div className="rounded-xl border border-border bg-background px-4 pt-3 pb-2.5">
            <div className="mb-2 flex items-center justify-between">
              <MinimapLegend />
              <span className="font-mono text-[11px] text-muted-foreground tabular-nums">
                {cursorIndex >= 0 ? `${cursorIndex + 1} / ${displaySteps.length}` : `${displaySteps.length} steps`}
              </span>
            </div>
            <TraceMinimap steps={displaySteps} annotations={trace.annotations} cursorStepId={cursorStepId} onJump={(step) => revealStep(step.id)} />
          </div>

          <div className="sticky top-0 z-20 -mx-2 mt-5 mb-4 flex items-center gap-2 border-b border-border-subtle bg-background/90 px-2 py-2.5 backdrop-blur">
            {VIEWS.map(([key, label]) => (
              <ToolbarButton key={key} active={view === key} onClick={() => setView(key)}>
                {label}
              </ToolbarButton>
            ))}
            <span className="flex-1 text-center text-[11.5px] text-muted-foreground">Select text in any step to comment on it.</span>
            <ToolbarButton
              active={expandAll}
              onClick={() => {
                setExpandAll(!expandAll);
                setRowChoice(new Map());
              }}
            >
              {expandAll ? <ChevronsDownUp size={13} /> : <ChevronsUpDown size={13} />}
              {expandAll ? "Collapse" : "Expand all"}
            </ToolbarButton>
          </div>

          <TraceTimeline rows={visibleRows} ann={ann} isExpanded={isExpanded} onToggle={toggleRow} />
          {visibleRows.length === 0 && <p className="py-12 text-center text-[13px] text-muted-foreground">No steps in this view.</p>}

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
        overview={<TraceOverview trace={trace} />}
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

function ToolbarButton({ active, onClick, children }: { active: boolean; onClick: () => void; children: ReactNode }) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={cn(
        "inline-flex h-7 cursor-pointer items-center gap-1.5 rounded-lg border px-2.5 text-[12.5px] font-medium transition-colors",
        active ? "border-foreground bg-foreground text-background" : "border-border bg-background text-dim hover:bg-surface",
      )}
    >
      {children}
    </button>
  );
}

function composerLabel(target: ComposerTarget, trace: RmTraceDetail): string {
  if (target.stepId === null) return "Comment on the whole trace";
  const step = trace.steps.find((s) => s.id === target.stepId)!;
  return target.quote ? `Comment on selection · step ${step.index}` : `Comment on step ${step.index} · ${step.role}`;
}
