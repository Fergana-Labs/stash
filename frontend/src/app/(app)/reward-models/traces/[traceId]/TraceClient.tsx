"use client";

import { useProductCheckpoint } from "@/components/ProductCheckpointContext";
import FloodgateComponent from "@/checkpoints/floodgate-2026-10-05/TraceClient";

import Link from "next/link";
import { ArrowLeft } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";
import { toast } from "sonner";
import { useBreadcrumbs } from "@/components/BreadcrumbContext";
import { useConfirm } from "@/components/ConfirmDialog";
import AnnotationComposer, { type ComposerTarget } from "@/components/reward-models/AnnotationComposer";
import TraceCommentMenu from "@/components/reward-models/TraceCommentMenu";
import AnnotationSidebar from "@/components/reward-models/AnnotationSidebar";
import { wbAssess } from "@/lib/workbench-api";
import TraceReviewAccess from "@/components/workbench/TraceReviewAccess";
import { TraceSkeleton } from "@/components/reward-models/RmSkeletons";
import TraceFlamegraph from "@/components/reward-models/TraceFlamegraph";
import { automaticActionScores, automaticAnnotationProgress } from "@/components/reward-models/automatic-credit";
import TraceMinimap from "@/components/reward-models/TraceMinimap";
import TraceScore from "@/components/reward-models/TraceScore";
import { type StepAnnotations } from "@/components/reward-models/TraceTimeline";
import { buildTraceLabels } from "@/components/reward-models/step-labels";
import { rubricSummary, stepReward } from "@/components/reward-models/step-rewards";
import { annotationStepIds, errorMessage, locateQuote, quoteForStep, relativeTime, sortAnnotations } from "@/components/reward-models/rm-text";
import { type Highlight } from "@/components/reward-models/source-anchors";
import { buildRows, rowSteps, type TraceRow } from "@/components/reward-models/trace-rows";
import TraceExplorer from "@/components/reward-models/TraceExplorer";
import { buildTraceOutline, groupPath, traceExplorerLevel, tracePhases } from "@/components/reward-models/trace-outline";
import { presentTrace } from "@/components/reward-models/trace-presentation";
import TraceScrollRail from "@/components/reward-models/TraceScrollRail";
import { TRACE_STEP_INSET } from "@/components/reward-models/trace-scroll";
import { useSectionSummaries } from "@/components/reward-models/use-section-summaries";
import { useTraceCompletion } from "@/components/reward-models/use-trace-completion";
import { taskCompletion } from "@/components/reward-models/task-completion";
import { useAuth } from "@/hooks/useAuth";
import { rmCreateAnnotation, rmDeleteAnnotation, rmGetTrace, rmUpdateAnnotation } from "@/lib/api";
import { cn } from "@/lib/utils";
import type { RmAnnotation, RmStep, RmTraceDetail } from "@/lib/types";

const FLASH_MS = 1400;
/** Highlight id for the not-yet-saved quote while the composer is open. */
const PENDING_ID = "pending";

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
  const [focusedSection, setFocusedSection] = useState<{ firstStepId: string; lastStepId: string } | null>(null);
  const [commentsOpen, setCommentsOpen] = useState(false);
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
        const top = container.scrollTop + element.getBoundingClientRect().top - Math.max(container.getBoundingClientRect().top, navigation.current.getBoundingClientRect().bottom) - TRACE_STEP_INSET;
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
  const { trail, children: sectionGroups } = traceExplorerLevel(groups, outlinePath);
  const browsingSections = sectionGroups.length > 0;
  // Retain global map titles if we enter a subsection before its root batch finishes.
  const assessmentGroups = [...new Map([...sectionGroups, ...trail, ...(groups.length > 1 ? groups : []), ...(!browsingSections ? tracePhases(groups).map(({ node }) => node) : [])].map((group) => [group.key, group])).values()];
  const assessments = useSectionSummaries(traceId, assessmentGroups);
  const completion = useTraceCompletion(traceId, trace?.steps ?? []);

  if (!trace && loadError) return <div role="alert" className="p-8 text-sm">Couldn’t load this trace. <button onClick={() => void load()} className="underline">Retry</button></div>;
  if (!trace || !user) return <TraceSkeleton />;
  const viewerId = user.id;
  const ordered = sortAnnotations(trace.annotations.filter((a) => a.comment !== null), trace.steps);
  const actionScores = automaticActionScores(evaluation, trace.steps);
  const annotationProgress = automaticAnnotationProgress(evaluation, trace.steps, actionScores);
  // Step labels say what each step is; the scores are built from them. Steps are numbered as the page shows them.
  const numberOf = (step: RmStep) => presentation.numberById.get(step.id) ?? step.index + 1;
  const labels = buildTraceLabels(trace.steps, numberOf);
  const stepScores = rubricSummary(trace.step_scores);
  const taskScores = new Map((stepScores?.episodes ?? []).map((task) => [task.task, task]));


  function annotationsOn(step: RmStep): RmAnnotation[] {
    return trace!.annotations.filter((a) => annotationStepIds(a).includes(step.id));
  }

  function highlightsFor(step: RmStep): Highlight[] {
    const saved = annotationsOn(step)
      .filter((a) => a.quote !== null)
      .sort((a, b) => Number(a.label_error) - Number(b.label_error))
      .flatMap((a) => {
        const range = locateQuote(step.content, quoteForStep(step.id, a.quote, a.step_id)!);
        return range ? [{ id: a.id, ...range, className: highlightClass(a, a.id === activeId) }] : [];
      });
    const pendingQuote = composer && quoteForStep(step.id, composer.quote, composer.stepId);
    if (!pendingQuote) return saved;
    const pending = locateQuote(step.content, pendingQuote);
    if (pending === null) return saved;
    return [{ id: PENDING_ID, ...pending, className: "rounded-[2px] bg-brand-300/45 text-inherit" }, ...saved];
  }

  /** Keep messages compact until the reader opens them. */
  function isExpanded(row: TraceRow): boolean {
    return rowChoice.get(row.key) ?? false;
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

  function openComposer(target: ComposerTarget) {
    setCommentsOpen(true);
    setComposer(target);
    window.getSelection()?.removeAllRanges();
  }

  /** Scrolls to a step, opening its row if needed. */
  function revealStep(stepId: string) {
    const row = rows.find((r) => rowSteps(r).some((s) => s.id === stepId));
    setOutlinePath(groupPath(groups, stepId));
    if (!row) return;
    if (!isExpanded(row)) toggleRow(row);
    setFlashStepId(stepId);
    requestAnimationFrame(() => {
      const element = document.getElementById(`step-${stepId}`);
      const container = scroller.current;
      if (!element || !container || !navigation.current) return;
      const top = container.scrollTop + element.getBoundingClientRect().top - Math.max(container.getBoundingClientRect().top, navigation.current.getBoundingClientRect().bottom) - TRACE_STEP_INSET;
      container.scrollTo({ top, behavior: "instant" });
    });
  }

  function focusAnnotation(annotation: RmAnnotation) {
    setActiveId(annotation.id);
    const stepId = annotationStepIds(annotation)[0];
    if (!stepId) {
      canvas.current!.scrollIntoView({ behavior: "smooth", block: "start" });
      return;
    }
    revealStep(stepId);
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
    actionScore: (step) => actionScores.get(step.id),
    commentCount: (step) => {
      const row = rows.find((r) => r.key === step.id);
      return new Set((row ? rowSteps(row) : [step]).flatMap((source) => annotationsOn(source).filter((a) => a.comment !== null).map((a) => a.id))).size;
    },
    hasQuotes: (step) => annotationsOn(step).some((a) => a.quote !== null) || !!(composer && quoteForStep(step.id, composer.quote, composer.stepId)),
    flashing: (step) => flashStepId === step.id,
    onComment: (step) => openComposer({ stepId: step.id, quote: null }),
    onViewComments: (step) => {
      const row = rows.find((r) => r.key === step.id);
      focusCard((row ? rowSteps(row) : [step]).flatMap((source) => annotationsOn(source).filter((a) => a.comment !== null).map((a) => a.id)));
    },
    onSelectAnnotation: focusCard,
    ...(labels.present && { taskHeading: labels.taskHeading, taskName: labels.taskName }),
    ...(stepScores !== null && {
      reward: stepReward,
      taskScore: (step: RmStep) => taskScores.get(labels.label(step)?.task_id ?? "") ?? null,
    }),
  };

  const mapStepId = (id: string) => presentation.mapSteps[(presentation.numberById.get(id) ?? 0) - 1]?.id ?? id;
  const mapAnnotations = trace.annotations.map((annotation) => ({
    ...annotation,
    step_id: annotation.step_id ? mapStepId(annotation.step_id) : null,
    quote: annotation.quote?.segments ? { ...annotation.quote, segments: annotation.quote.segments.map((segment) => ({ ...segment, step_id: mapStepId(segment.step_id) })) } : annotation.quote,
  }));

  return (
    <div className="relative flex h-full min-h-0">
      <TraceScrollRail groups={groups} path={outlinePath} rows={rows} onPath={setOutlinePath} onStep={revealStep} focusedStepId={browsingSections ? focusedSection?.firstStepId : undefined}
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
              <TraceScore evaluation={evaluation} error={loadError} onRescore={evaluation?.owner_user_id === viewerId ? () => wbAssess(traceId).then(load) : undefined} />
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

          <TraceMinimap steps={presentation.mapSteps} annotations={mapAnnotations} actionScores={actionScores} annotationStatus={annotationProgress.label} unscoredReasons={annotationProgress.unscoredReasons} completion={taskCompletion(completion.tasks, presentation.numberById)} completionLoading={completion.loading} focusedRange={browsingSections && focusedSection ? { first: (presentation.numberById.get(focusedSection.firstStepId) ?? 1) - 1, last: (presentation.numberById.get(focusedSection.lastStepId) ?? 1) - 1 } : undefined} scroller={scroller} navigation={navigation} onJump={(index) => revealStep(presentation.mapSteps[index].id)} />


        </div>
        </div>
        <div ref={scroller} data-trace-scroll className="scroll-thin min-h-0 flex-1 overflow-y-auto">
        <TraceCommentMenu steps={trace.steps} onComment={openComposer}>
        <div ref={canvas} className={cn("relative mx-auto max-w-5xl px-6 pt-2", browsingSections ? "pb-3" : "pb-12")}>
          <TraceFlamegraph spans={trace.spans} onJump={(index) => revealStep(trace.steps[index].id)} />
          <TraceExplorer
            groups={groups} path={outlinePath} assessments={assessments} onSectionFocus={setFocusedSection}
            onPath={(path, options) => {
              setOutlinePath(path);
              if (options?.scroll === false) return;
              const level = traceExplorerLevel(groups, path);
              const first = level.current && !level.children.length ? rowSteps(level.current.rows[0])[0] : null;
              requestAnimationFrame(() => {
                const container = scroller.current;
                const target = first ? document.getElementById(`step-${first.id}`) : null;
                container?.scrollTo({ top: target && container ? container.scrollTop + target.getBoundingClientRect().top - container.getBoundingClientRect().top - TRACE_STEP_INSET : 0, behavior: "instant" });
              });
            }}
            ann={ann} isExpanded={isExpanded} onToggle={toggleRow}
          />
          {rows.length === 0 && <p className="py-12 text-center text-[13px] text-muted-foreground">No steps in this trace.</p>}
        </div>
        </TraceCommentMenu>
        </div>
      </div>


      <AnnotationSidebar
        visible={commentsOpen}
        onClose={() => setCommentsOpen(false)}
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

function composerLabel(target: ComposerTarget, trace: RmTraceDetail, numbers: Map<string, number>): string {
  if (target.quote?.segments) {
    const selectedNumbers = [...new Set(target.quote.segments.map((segment) => numbers.get(segment.step_id)).filter((number) => number !== undefined))];
    return `Comment on selection in ${selectedNumbers.length === 1 ? `step ${selectedNumbers[0]}` : `steps ${selectedNumbers[0]}–${selectedNumbers.at(-1)}`}`;
  }
  if (target.stepId === null) return "Comment on the whole trace";
  const step = trace.steps.find((s) => s.id === target.stepId)!;
  const number = numbers.get(step.id);
  const label = number ? `step ${number}${step.role === "tool" ? " output" : ""}` : "message";
  return target.quote ? `Comment on selection in ${label}` : `Comment on ${label}`;
}

export default function TraceClient(props: React.ComponentProps<typeof LatestTraceClient>) {
  return useProductCheckpoint() === "floodgate-2026-10-05"
    ? <FloodgateComponent {...props} />
    : <LatestTraceClient key={props.traceId} {...props} />;
}
