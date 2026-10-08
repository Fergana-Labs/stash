"use client";

import { useProductCheckpoint } from "@/components/ProductCheckpointContext";
import FloodgateComponent from "@/checkpoints/floodgate-2026-10-05/TraceClient";

import Link from "next/link";
import { ArrowLeft } from "lucide-react";
import { useCallback, useEffect, useRef, useState, type MouseEvent } from "react";
import { toast } from "sonner";
import { useBreadcrumbs } from "@/components/BreadcrumbContext";
import { useConfirm } from "@/components/ConfirmDialog";
import AnnotationComposer, { type ComposerTarget } from "@/components/reward-models/AnnotationComposer";
import AnnotationSidebar from "@/components/reward-models/AnnotationSidebar";
import { wbEvaluation, wbAssess } from "@/lib/workbench-api";
import { useWorkbenchLoad } from "@/components/workbench/workbench-ui";
import { Button } from "@/components/ui/button";
import TraceReviewAccess from "@/components/workbench/TraceReviewAccess";
import { TraceSkeleton } from "@/components/reward-models/RmSkeletons";
import TraceFlamegraph from "@/components/reward-models/TraceFlamegraph";
import { automaticActionScores, automaticAnnotationProgress } from "@/components/reward-models/automatic-credit";
import TraceMinimap from "@/components/reward-models/TraceMinimap";
import TraceTimeline, { type StepAnnotations } from "@/components/reward-models/TraceTimeline";
import { errorMessage, locateQuote, quoteFromOffsets, relativeTime, sortAnnotations } from "@/components/reward-models/rm-text";
import { domSourceOffset, type Highlight } from "@/components/reward-models/source-anchors";
import { buildRows, rowSteps, type TraceRow } from "@/components/reward-models/trace-rows";
import { traceScrollMarkers } from "@/components/reward-models/trace-scroll";
import { useAuth } from "@/hooks/useAuth";
import { rmCreateAnnotation, rmDeleteAnnotation, rmGetTrace, rmUpdateAnnotation } from "@/lib/api";
import { cn } from "@/lib/utils";
import type { RmAnnotation, RmStep, RmTraceDetail } from "@/lib/types";
import ConversationScrollRail from "@/components/ConversationScrollRail";

const FLASH_MS = 1400;
/** Highlight id for the not-yet-saved quote while the composer is open. */
const PENDING_ID = "pending";

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

function LatestTraceClient({ traceId }: { traceId: string }) {
  const { user } = useAuth();
  const confirm = useConfirm();
  const [trace, setTrace] = useState<RmTraceDetail | null>(null);
  const evaluationLoader = useCallback(() => wbEvaluation(traceId), [traceId]);
  const { data: evaluation, reload: reloadEvaluation } = useWorkbenchLoad(evaluationLoader, 5000);
  const [commentsOpen, setCommentsOpen] = useState(true);
  const [composer, setComposer] = useState<ComposerTarget | null>(null);
  const [activeId, setActiveId] = useState<string | null>(null);
  const [flashStepId, setFlashStepId] = useState<string | null>(null);
  const [pendingAnnotationId, setPendingAnnotationId] = useState<string | null>(null);
  // Rows the user opened (true) or closed (false) by hand; the rest follow their default.
  const [rowChoice, setRowChoice] = useState<Map<string, boolean>>(new Map());
  const navigation = useRef<HTMLDivElement | null>(null);
  const canvas = useRef<HTMLDivElement | null>(null);
  const scroller = useRef<HTMLDivElement | null>(null);
  const openedHash = useRef<string | null>(null);

  useBreadcrumbs(
    [{ label: "Traces", href: "/reward-models" }, { label: trace?.title ?? "Trace" }],
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
    const timer = setInterval(() => { if (document.visibilityState === "visible") void load(); }, 5000);
    return () => clearInterval(timer);
  }, [load]);

  useEffect(() => {
    if (flashStepId === null) return;
    const timer = setTimeout(() => setFlashStepId(null), FLASH_MS);
    return () => clearTimeout(timer);
  }, [flashStepId]);

  // Review records and load receipts link to captured events, including tool
  // results nested inside initially collapsed rows.
  useEffect(() => {
    if (!trace) return;
    let frame = 0;
    const revealHash = () => {
      const hash = window.location.hash;
      if (!hash.startsWith("#step-") || openedHash.current === hash) return;
      const stepId = hash.slice("#step-".length);
      const row = buildRows(trace.steps).find((candidate) => rowSteps(candidate).some((step) => step.id === stepId));
      if (!row) return;
      openedHash.current = hash;
      setRowChoice((current) => new Map(current).set(row.key, true));
      setFlashStepId(stepId);
      frame = requestAnimationFrame(() => {
        const element = document.getElementById(`step-${stepId}`);
        const container = scroller.current;
        if (!element || !container || !navigation.current) return;
        const top = container.scrollTop + element.getBoundingClientRect().top - Math.max(container.getBoundingClientRect().top, navigation.current.getBoundingClientRect().bottom) - 12;
        container.scrollTo({ top, behavior: "instant" });
      });
    };
    revealHash();
    window.addEventListener("hashchange", revealHash);
    return () => { cancelAnimationFrame(frame); window.removeEventListener("hashchange", revealHash); };
  }, [trace]);

  const closeComposer = useCallback(() => setComposer(null), []);

  if (!trace || !user) return <TraceSkeleton />;
  const viewerId = user.id;
  const ordered = sortAnnotations(trace.annotations.filter((a) => a.comment !== null), trace.steps);
  const rows = buildRows(trace.steps);
  const current = evaluation?.current;
  const score = current?.outcome !== "insufficient_evidence" ? current?.outcome_probabilities?.success : null;
  const actionScores = automaticActionScores(evaluation, trace.steps);
  const annotationProgress = automaticAnnotationProgress(evaluation, trace.steps, actionScores);


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
    return rowSteps(row).some((s) => annotationsOn(s).length > 0);
  }

  function toggleRow(row: TraceRow) {
    setRowChoice(new Map(rowChoice).set(row.key, !isExpanded(row)));
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

  /** Scrolls to a step, opening its row if needed. */
  function revealStep(stepId: string) {
    const row = rows.find((r) => rowSteps(r).some((s) => s.id === stepId));
    if (!row) return;
    if (!isExpanded(row) && row.kind !== "assistant") toggleRow(row);
    setFlashStepId(stepId);
    requestAnimationFrame(() => {
      const element = document.getElementById(`step-${stepId}`);
      const container = scroller.current;
      if (!element || !container || !navigation.current) return;
      const top = container.scrollTop + element.getBoundingClientRect().top - Math.max(container.getBoundingClientRect().top, navigation.current.getBoundingClientRect().bottom) - 12;
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
    actionScore: (step) => actionScores.get(step.id),
    highlights: highlightsFor,
    commentCount: (step) => annotationsOn(step).filter((a) => a.comment !== null).length,
    hasQuotes: (step) => annotationsOn(step).some((a) => a.quote !== null) || composer?.stepId === step.id,
    flashing: (step) => flashStepId === step.id,
    onComment: (step) => openComposer(step.id),
    onSelectAnnotation: focusCard,
  };

  const scrollMarkers = traceScrollMarkers(rows);

  return (
    <div className="flex h-full min-h-0">
      <ConversationScrollRail items={scrollMarkers} scroller={scroller} header={navigation} onJump={(item) => revealStep(item.targetId.slice("step-".length))} />
      <div className="flex min-h-0 min-w-0 flex-1 flex-col">
        <div ref={navigation} className="z-20 shrink-0 border-b border-border bg-background px-6 py-2">
        <div className="mx-auto max-w-5xl space-y-2">
          <header className="flex h-8 items-center gap-3">
            <Link href="/reward-models" aria-label="Back to traces" title="Back to traces" className="inline-flex size-7 shrink-0 items-center justify-center rounded-md text-muted-foreground hover:bg-surface hover:text-foreground">
              <ArrowLeft className="size-4" aria-hidden="true" />
            </Link>
            <div className="flex min-w-0 flex-1 items-baseline gap-2.5">
              <h1 title={trace.title} className="m-0 min-w-0 truncate font-display text-[18px] leading-snug font-semibold tracking-tight text-foreground">{trace.title}</h1>
              <span className="shrink-0 whitespace-nowrap text-[11px] text-muted-foreground">imported {relativeTime(trace.created_at)}</span>
            </div>
            <div className="flex shrink-0 items-center gap-1.5">
              <div className="mr-2 flex items-baseline gap-1.5 whitespace-nowrap" title="Automatic trace annotation: estimated probability of success (0–1)"><span className="text-[10px] text-muted-foreground">Trace score</span><span className="font-mono text-[16px] font-medium text-foreground tabular-nums">{score == null ? "—" : score.toFixed(2)}</span></div>
              {evaluation?.queue?.status === "failed" && evaluation.owner_user_id === viewerId && <Button size="xs" variant="ghost" onClick={() => void wbAssess(traceId).then(reloadEvaluation).catch((e) => toast.error(errorMessage(e)))}>Retry scoring</Button>}
              <TraceReviewAccess traceId={traceId} viewerId={viewerId} />
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

          <TraceMinimap steps={trace.steps} annotations={trace.annotations} actionScores={actionScores} annotationStatus={annotationProgress.label} unscoredReasons={annotationProgress.unscoredReasons} scroller={scroller} navigation={navigation} onJump={(index) => revealStep(trace.steps[index].id)} />

        </div>
        </div>
        <div ref={scroller} className="scroll-thin min-h-0 flex-1 overflow-y-auto">
        <div ref={canvas} className="relative mx-auto max-w-5xl px-6 pt-2 pb-[60vh]" onMouseUp={onCanvasMouseUp}>
          <TraceFlamegraph spans={trace.spans} onJump={(index) => revealStep(trace.steps[index].id)} />
          <TraceTimeline rows={rows} ann={ann} isExpanded={isExpanded} onToggle={toggleRow} />
          {rows.length === 0 && <p className="py-12 text-center text-[13px] text-muted-foreground">No steps in this trace.</p>}
        </div>
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

function composerLabel(target: ComposerTarget, trace: RmTraceDetail): string {
  if (target.stepId === null) return "Comment on the whole trace";
  const step = trace.steps.find((s) => s.id === target.stepId)!;
  return target.quote ? `Comment on selection in step ${step.index + 1}` : `Comment on step ${step.index + 1} (${step.role})`;
}

export default function TraceClient(props: React.ComponentProps<typeof LatestTraceClient>) {
  return useProductCheckpoint() === "floodgate-2026-10-05"
    ? <FloodgateComponent {...props} />
    : <LatestTraceClient {...props} />;
}
