"use client";

import Link from "next/link";
import { useCallback, useEffect, useRef, useState, type MouseEvent, type ReactNode } from "react";
import { toast } from "sonner";
import { useBreadcrumbs } from "@/components/BreadcrumbContext";
import { useConfirm } from "@/components/ConfirmDialog";
import AnnotationComposer, { type ComposerTarget } from "@/components/reward-models/AnnotationComposer";
import AnnotationSidebar from "@/components/reward-models/AnnotationSidebar";
import { TraceSkeleton } from "@/components/reward-models/RmSkeletons";
import TraceFlamegraph from "@/components/reward-models/TraceFlamegraph";
import TraceMinimap from "@/components/reward-models/TraceMinimap";
import TraceTimeline, { type StepAnnotations } from "@/components/reward-models/TraceTimeline";
import { errorMessage, locateQuote, quoteFromOffsets, relativeTime, sortAnnotations } from "@/components/reward-models/rm-text";
import { domSourceOffset, type Highlight } from "@/components/reward-models/source-anchors";
import { buildRows, rowSteps, type TraceRow } from "@/components/reward-models/trace-rows";
import { visibleStepElement } from "@/components/reward-models/trace-scroll";
import { useAuth } from "@/hooks/useAuth";
import { rmCreateAnnotation, rmDeleteAnnotation, rmGetTrace, rmUpdateAnnotation } from "@/lib/api";
import { cn } from "@/lib/utils";
import type { RmAnnotation, RmStep, RmTraceDetail } from "@/lib/types";

const FLASH_MS = 1400;
/** Highlight id for the not-yet-saved quote while the composer is open. */
const PENDING_ID = "pending";

type View = "all" | "conversation" | "tools";

const VIEWS: [View, string][] = [
  ["all", "All"],
  ["conversation", "Conversation"],
  ["tools", "Tools"],
];

function stepContentElement(node: Node | null): HTMLElement | null {
  const element = node instanceof HTMLElement ? node : node?.parentElement;
  return element?.closest<HTMLElement>("[data-step-content]") ?? null;
}

function highlightClass(a: RmAnnotation, active: boolean): string {
  return cn(
    "cursor-pointer rounded-[2px] text-inherit transition-colors",
    a.label_error
      ? "bg-transparent underline decoration-muted-foreground/50 decoration-dashed underline-offset-4"
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
  const [commentsOpen, setCommentsOpen] = useState(true);
  const [composer, setComposer] = useState<ComposerTarget | null>(null);
  const [activeId, setActiveId] = useState<string | null>(null);
  const [flashStepId, setFlashStepId] = useState<string | null>(null);
  const [pendingAnnotationId, setPendingAnnotationId] = useState<string | null>(null);
  const [view, setView] = useState<View>("all");
  const [expandAll, setExpandAll] = useState(false);
  // Rows the user opened (true) or closed (false) by hand; the rest follow their default.
  const [rowChoice, setRowChoice] = useState<Map<string, boolean>>(new Map());
  const navigation = useRef<HTMLDivElement | null>(null);
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

  const closeComposer = useCallback(() => setComposer(null), []);

  if (!trace || !user) return <TraceSkeleton />;
  const viewerId = user.id;
  const ordered = sortAnnotations(trace.annotations.filter((a) => a.comment !== null), trace.steps);
  const rows = buildRows(trace.steps);

  function annotationsOn(step: RmStep): RmAnnotation[] {
    return trace!.annotations.filter((a) => a.step_id === step.id);
  }

  function highlightsFor(step: RmStep): Highlight[] {
    const saved = annotationsOn(step)
      .filter((a) => a.quote !== null)
      .sort((a, b) => Number(a.label_error) - Number(b.label_error))
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

  function changeView(nextView: View) {
    if (nextView === view) return;
    const container = scroller.current!;
    const header = navigation.current!;
    const current = visibleStepElement(container, header);
    setView(nextView);
    if (current === null) return;

    const currentStep = trace!.steps.find((step) => `step-${step.id}` === current.id)!;
    const candidates = rows.filter((row) => inView(row, nextView));
    if (candidates.length === 0) return;
    const staysVisible = candidates.some((row) => rowSteps(row).some((step) => step.id === currentStep.id));
    let target = currentStep;
    if (!staysVisible) {
      target = rowSteps(candidates[0])[0];
      for (const row of candidates) {
        const step = rowSteps(row)[0];
        if (Math.abs(step.index - currentStep.index) < Math.abs(target.index - currentStep.index)) target = step;
      }
    }
    const offset = staysVisible
      ? current.getBoundingClientRect().top - container.getBoundingClientRect().top
      : header.offsetHeight + 12;
    requestAnimationFrame(() => {
      const element = document.getElementById(`step-${target.id}`)!;
      const top = container.scrollTop + element.getBoundingClientRect().top - container.getBoundingClientRect().top - offset;
      container.scrollTo({ top, behavior: "instant" });
    });
  }

  async function submitComment(target: ComposerTarget, comment: string) {
    try {
      await rmCreateAnnotation(traceId, {
        ...(target.stepId !== null && { step_id: target.stepId }),
        ...(target.quote !== null && { quote: target.quote }),
        comment,
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

  function openComposer(stepId: string | null) {
    setCommentsOpen(true);
    setComposer({ stepId, quote: null });
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

    setCommentsOpen(true);
    setComposer({ stepId: step.id, quote: quoteFromOffsets(step.content, start, end) });
  }

  /** Scrolls to a step, opening its row and clearing a filter that hides it. */
  function revealStep(stepId: string) {
    const row = rows.find((r) => rowSteps(r).some((s) => s.id === stepId))!;
    if (!inView(row, view)) setView("all");
    if (!isExpanded(row) && row.kind !== "assistant") toggleRow(row);
    setFlashStepId(stepId);
    requestAnimationFrame(() => {
      const element = document.getElementById(`step-${stepId}`);
      const container = scroller.current;
      if (!element || !container || !navigation.current) return;
      const top = container.scrollTop + element.getBoundingClientRect().top - container.getBoundingClientRect().top - navigation.current.offsetHeight - 12;
      container.scrollTo({ top, behavior: "instant" });
    });
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
    setCommentsOpen(true);
    const id = ids.find((i) => i !== PENDING_ID);
    if (id === undefined) return;
    setActiveId(id);
    document.getElementById(`annotation-${id}`)?.scrollIntoView({ behavior: "smooth", block: "nearest" });
  }

  const ann: StepAnnotations = {
    highlights: highlightsFor,
    commentCount: (step) => annotationsOn(step).filter((a) => a.comment !== null).length,
    hasQuotes: (step) => annotationsOn(step).some((a) => a.quote !== null) || composer?.stepId === step.id,
    flashing: (step) => flashStepId === step.id,
    onComment: (step) => openComposer(step.id),
    onSelectAnnotation: focusCard,
  };

  const visibleRows = rows.filter((row) => inView(row, view));

  return (
    <div className="flex h-full min-h-0">
      <div ref={scroller} className="scroll-thin min-w-0 flex-1 overflow-y-auto">
        <div ref={canvas} className="relative mx-auto max-w-4xl px-8 pt-6 pb-24" onMouseUp={onCanvasMouseUp}>
          <Link href="/reward-models" aria-label="Back to traces" className="inline-flex h-7 items-center rounded-md border border-border px-2.5 text-[12px] text-muted-foreground hover:bg-surface hover:text-foreground">
            Back
          </Link>

          <header className="mt-3 mb-5 flex items-start gap-4">
            <div className="min-w-0 flex-1">
              <h1 className="m-0 font-display text-[21px] leading-snug font-semibold tracking-tight text-foreground">{trace.title}</h1>
              <div className="mt-1.5 flex flex-wrap items-center gap-2 text-[12px] text-muted-foreground">
                <span>imported {relativeTime(trace.created_at)}</span>
              </div>
            </div>
            <div className="flex shrink-0 items-center gap-1.5 pt-1">
              <button
                type="button"
                aria-expanded={commentsOpen}
                aria-controls="trace-comments"
                onClick={() => {
                  setCommentsOpen(!commentsOpen);
                  if (!commentsOpen) {
                    requestAnimationFrame(() => document.getElementById("trace-comments")?.scrollIntoView({ block: "nearest" }));
                  }
                }}
                className="inline-flex h-7 cursor-pointer items-center gap-1 rounded-md border border-border bg-background px-2 text-[12px] text-muted-foreground transition-colors hover:border-foreground/20 hover:text-foreground"
              >
                Comments{ordered.length > 0 && ` (${ordered.length})`}
              </button>
            </div>
          </header>

          <div ref={navigation} className="sticky top-0 z-20 bg-background pb-2">
            <TraceMinimap steps={trace.steps} annotations={trace.annotations} scroller={scroller} navigation={navigation} onJump={(index) => revealStep(trace.steps[index].id)} />
            <TraceFlamegraph spans={trace.spans} onJump={(index) => revealStep(trace.steps[index].id)} />

            <div className="-mx-2 mt-1 flex items-center gap-2 border-b border-border-subtle bg-background px-2 py-1.5">
              {VIEWS.map(([key, label]) => (
                <ToolbarButton key={key} active={view === key} onClick={() => changeView(key)}>
                  {label}
                </ToolbarButton>
              ))}
              <span className="flex-1" />
              <ToolbarButton
                active={expandAll}
                onClick={() => {
                  setExpandAll(!expandAll);
                  setRowChoice(new Map());
                }}
              >
                {expandAll ? "Collapse" : "Expand all"}
              </ToolbarButton>
            </div>

          </div>

          <TraceTimeline rows={visibleRows} ann={ann} isExpanded={isExpanded} onToggle={toggleRow} />
          {visibleRows.length === 0 && <p className="py-12 text-center text-[13px] text-muted-foreground">No steps in this view.</p>}
        </div>
      </div>

      <AnnotationSidebar
        visible={commentsOpen}
        onClose={() => setCommentsOpen(false)}
        onAddComment={() => openComposer(null)}
        composer={
          composer && (
            <AnnotationComposer
              key={JSON.stringify(composer)}
              target={composer}
              label={composerLabel(composer, trace)}
              onCancel={closeComposer}
              onSubmit={(comment) => submitComment(composer, comment)}
            />
          )
        }
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
      aria-pressed={active}
      className={cn(
        "inline-flex h-7 cursor-pointer items-center gap-1.5 border-b-2 px-2 text-[12px] transition-colors",
        active ? "border-foreground font-medium text-foreground" : "border-transparent text-muted-foreground hover:text-foreground",
      )}
    >
      {children}
    </button>
  );
}

function composerLabel(target: ComposerTarget, trace: RmTraceDetail): string {
  if (target.stepId === null) return "Comment on the whole trace";
  const step = trace.steps.find((s) => s.id === target.stepId)!;
  return target.quote ? `Comment on selection in step ${step.index + 1}` : `Comment on step ${step.index + 1} (${step.role})`;
}
