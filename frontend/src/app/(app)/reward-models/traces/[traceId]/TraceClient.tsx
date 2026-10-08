"use client";

import { useProductCheckpoint } from "@/components/ProductCheckpointContext";
import FloodgateComponent from "@/checkpoints/floodgate-2026-10-05/TraceClient";

import Link from "next/link";
import { ArrowLeft } from "lucide-react";
import { useCallback, useEffect, useRef, useState, type MouseEvent, type ReactNode } from "react";
import { toast } from "sonner";
import { useBreadcrumbs } from "@/components/BreadcrumbContext";
import { useConfirm } from "@/components/ConfirmDialog";
import AnnotationComposer, { type ComposerTarget } from "@/components/reward-models/AnnotationComposer";
import AnnotationSidebar from "@/components/reward-models/AnnotationSidebar";
import { wbAssess } from "@/lib/workbench-api";
import { Button } from "@/components/ui/button";
import TraceReviewAccess from "@/components/workbench/TraceReviewAccess";
import { TraceSkeleton } from "@/components/reward-models/RmSkeletons";
import TraceFlamegraph from "@/components/reward-models/TraceFlamegraph";
import { automaticActionScores, automaticAnnotationProgress } from "@/components/reward-models/automatic-credit";
import TraceMinimap from "@/components/reward-models/TraceMinimap";
import TraceScore from "@/components/reward-models/TraceScore";
import { TraceContext, type StepAnnotations } from "@/components/reward-models/TraceTimeline";
import { TraceLabelSummary } from "@/components/reward-models/StepLabels";
import { ScoringExplainer } from "@/components/reward-models/StepRewards";
import { buildTraceLabels } from "@/components/reward-models/step-labels";
import { rubricSummary, stepReward } from "@/components/reward-models/step-rewards";
import { errorMessage, locateQuote, quoteFromOffsets, relativeTime, sortAnnotations } from "@/components/reward-models/rm-text";
import { domSourceOffset, type Highlight } from "@/components/reward-models/source-anchors";
import { buildRows, rowSteps, type TraceRow } from "@/components/reward-models/trace-rows";
import TraceExplorer from "@/components/reward-models/TraceExplorer";
import { buildTraceOutline, groupPath, resolveGroupPath } from "@/components/reward-models/trace-outline";
import { presentTrace } from "@/components/reward-models/trace-presentation";
import TraceScrollRail from "@/components/reward-models/TraceScrollRail";
import { useSectionSummaries } from "@/components/reward-models/use-section-summaries";
import { useAuth } from "@/hooks/useAuth";
import { rmCreateAnnotation, rmDeleteAnnotation, rmGetTrace, rmUpdateAnnotation } from "@/lib/api";
import { cn } from "@/lib/utils";
import type { RmAnnotation, RmStep, RmTraceDetail } from "@/lib/types";

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
  const evaluation = trace?.automatic_evaluation ?? null;
  const [loadError, setLoadError] = useState<string | null>(null);
  const [outlinePath, setOutlinePath] = useState<string[]>([]);
  const [commentsOpen, setCommentsOpen] = useState(false);
  const [showLabels, setShowLabels] = useState(true);
  const [showScores, setShowScores] = useState(true);
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
      setTrace(await rmGetTrace(traceId, true));
      setLoadError(null);
    } catch (e) {
      setLoadError(errorMessage(e));
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
      setOutlinePath(groupPath(buildTraceOutline(presentTrace(trace.steps).rows), stepId));
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

  const presentation = presentTrace(trace?.steps ?? []);
  const { rows } = presentation;
  const groups = buildTraceOutline(rows);
  const focusedGroup = resolveGroupPath(groups, outlinePath).at(-1);
  const browsingSections = focusedGroup ? focusedGroup.children.length > 0 : !(groups.length === 1 && !groups[0].children.length && groups[0].rows.length <= 8);
  const sectionGroups = browsingSections ? focusedGroup?.children ?? groups : [];
  // Retain global map titles if we enter a subsection before its root batch finishes.
  const assessmentGroups = [...new Map([...(groups.length > 1 ? groups : []), ...sectionGroups].map((group) => [group.key, group])).values()];
  const assessments = useSectionSummaries(traceId, assessmentGroups);

  if (!trace && loadError) return <div role="alert" className="p-8 text-sm">Couldn’t load this trace. <button onClick={() => void load()} className="underline">Retry</button></div>;
  if (!trace || !user) return <TraceSkeleton />;
  const viewerId = user.id;
  const ordered = sortAnnotations(trace.annotations.filter((a) => a.comment !== null), trace.steps);
  const actionScores = automaticActionScores(evaluation, trace.steps);
  const annotationProgress = automaticAnnotationProgress(evaluation, trace.steps, actionScores);
  // Step labels say what each step is; the scores are built from them. Steps are numbered as the page shows them.
  const numberOf = (step: RmStep) => presentation.numberById.get(step.id) ?? step.index + 1;
  const labels = buildTraceLabels(trace.steps, numberOf);
  const labelsOn = labels.present && showLabels;
  const stepScores = rubricSummary(trace.step_scores);
  const scoresOn = stepScores !== null && showScores;
  const taskScores = new Map((stepScores?.episodes ?? []).map((task) => [task.task, task]));


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

  /** Messages start readable; context and tool details open on demand. */
  function isExpanded(row: TraceRow): boolean {
    const choice = rowChoice.get(row.key);
    if (choice !== undefined) return choice;
    if (row.kind !== "prompt") return false;
    const index = rows.findIndex((item) => item.key === row.key);
    const previous = rows[index - 1];
    return !(previous?.kind === "prompt" && previous.step.content === row.step.content && previous.step.index + 1 === row.step.index);
  }

  function openRows(rows: TraceRow[]) {
    setRowChoice((current) => {
      const next = new Map(current);
      for (const row of rows) next.set(row.key, true);
      return next;
    });
  }

  function toggleRow(row: TraceRow) {
    setRowChoice((current) => new Map(current).set(row.key, !isExpanded(row)));
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
    const row = [...rows, ...presentation.context.map((step): TraceRow => ({ kind: "system", key: step.id, step }))].find((r) => rowSteps(r).some((s) => s.id === stepId));
    setOutlinePath(groupPath(groups, stepId));
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
    stepNumber: (step) => presentation.numberById.get(step.id),
    highlights: highlightsFor,
    commentCount: (step) => {
      const row = rows.find((r) => r.key === step.id);
      return (row ? rowSteps(row) : [step]).reduce((count, source) => count + annotationsOn(source).filter((a) => a.comment !== null).length, 0);
    },
    hasQuotes: (step) => annotationsOn(step).some((a) => a.quote !== null) || composer?.stepId === step.id,
    flashing: (step) => flashStepId === step.id,
    onComment: (step) => openComposer(step.id),
    onSelectAnnotation: focusCard,
    ...(labelsOn && { labelChips: labels.chips, taskHeading: labels.taskHeading, onJumpToStep: revealStep }),
    ...(scoresOn && {
      reward: stepReward,
      taskScore: (step: RmStep) => taskScores.get(labels.label(step)?.task_id ?? "") ?? null,
      stepNumberOf: (chunk: string) => { const step = labels.stepForChunk(chunk); return step ? numberOf(step) : null; },
      onJumpToChunk: (chunk: string) => { const step = labels.stepForChunk(chunk); if (step) revealStep(step.id); },
    }),
  };

  return (
    <div className="flex h-full min-h-0">
      <TraceScrollRail groups={groups} path={outlinePath} rows={rows} onPath={setOutlinePath} onOpenRows={openRows} onStep={revealStep}
        copy={assessments.copy} stepNumber={(step) => presentation.numberById.get(step.id) ?? step.index + 1} scroller={scroller} />
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
              <TraceScore evaluation={evaluation} error={loadError} />
              {evaluation?.queue?.status === "failed" && evaluation.owner_user_id === viewerId && <Button size="xs" variant="ghost" onClick={() => void wbAssess(traceId).then(load).catch((e) => toast.error(errorMessage(e)))}>Retry scoring</Button>}
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
              <TraceReviewAccess traceId={traceId} viewerId={viewerId} />
            </div>
          </header>

          <TraceMinimap steps={presentation.mapSteps} annotations={trace.annotations.map((annotation) => ({ ...annotation, step_id: annotation.step_id ? presentation.mapSteps[(presentation.numberById.get(annotation.step_id) ?? 0) - 1]?.id ?? annotation.step_id : null }))} actionScores={actionScores} annotationStatus={annotationProgress.label} unscoredReasons={annotationProgress.unscoredReasons} scroller={scroller} navigation={navigation} onJump={(index) => revealStep(presentation.mapSteps[index].id)} />
          {(labels.present || stepScores !== null) && (
            <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
              {labelsOn && <TraceLabelSummary items={labels.summary} onJump={revealStep} />}
              <span className="flex-1" />
              {scoresOn && <ScoringExplainer />}
              {labels.present && <ViewToggle active={showLabels} onClick={() => setShowLabels(!showLabels)}>Labels</ViewToggle>}
              {stepScores !== null && <ViewToggle active={showScores} onClick={() => setShowScores(!showScores)}>Scores</ViewToggle>}
            </div>
          )}
          {evaluation?.queue?.status === "failed" && evaluation.queue.error && (
            <p className="m-0 text-[12px] text-muted-foreground">This trace was not annotated. {evaluation.queue.error}</p>
          )}

        </div>
        </div>
        <div ref={scroller} className="scroll-thin min-h-0 flex-1 overflow-y-auto">
        <div ref={canvas} className={cn("relative mx-auto max-w-5xl px-6 pt-2", browsingSections ? "pb-3" : "pb-[60vh]")} onMouseUp={onCanvasMouseUp}>
          <TraceFlamegraph spans={trace.spans} onJump={(index) => revealStep(trace.steps[index].id)} />
          <TraceContext steps={presentation.context} ann={ann} isExpanded={isExpanded} onToggle={toggleRow} />
          <TraceExplorer
            groups={groups} path={outlinePath} assessments={assessments}
            onPath={(path) => { setOutlinePath(path); scroller.current?.scrollTo({ top: 0, behavior: "instant" }); }}
            ann={ann} isExpanded={isExpanded} onToggle={toggleRow} onOpenRows={openRows}
          />
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
              label={composerLabel(composer, trace, presentation.numberById)}
              onCancel={closeComposer}
              onSubmit={(comment) => submitComment(composer, comment)}
            />
          )
        }
        annotations={ordered}
        steps={presentation.commentSteps}
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

function ViewToggle({ active, onClick, children }: { active: boolean; onClick: () => void; children: ReactNode }) {
  return (
    <button type="button" onClick={onClick} aria-pressed={active}
      className={cn("inline-flex h-6 cursor-pointer items-center border-b-2 px-1.5 text-[12px] transition-colors",
        active ? "border-foreground font-medium text-foreground" : "border-transparent text-muted-foreground hover:text-foreground")}>
      {children}
    </button>
  );
}

function composerLabel(target: ComposerTarget, trace: RmTraceDetail, numbers: Map<string, number>): string {
  if (target.stepId === null) return "Comment on the whole trace";
  const step = trace.steps.find((s) => s.id === target.stepId)!;
  const number = numbers.get(step.id);
  const label = number ? `step ${number}${step.role === "tool" ? " output" : ""}` : "instructions";
  return target.quote ? `Comment on selection in ${label}` : `Comment on ${label}`;
}

export default function TraceClient(props: React.ComponentProps<typeof LatestTraceClient>) {
  return useProductCheckpoint() === "floodgate-2026-10-05"
    ? <FloodgateComponent {...props} />
    : <LatestTraceClient key={props.traceId} {...props} />;
}
