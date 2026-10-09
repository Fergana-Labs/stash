"use client";

import { useRef, useState, type ReactNode } from "react";
import { Check, Play, Square } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { errorMessage } from "@/components/reward-models/rm-text";
import { cn } from "@/lib/utils";
import { imFit, imGrade, imSetHead, type ExampleSource } from "@/lib/intuition-api";
import { DEFAULT_L2, pct } from "./im-helpers";
import { Bar, Callout, inputClass, Spinner, useIntuition } from "./im-ui";
import MetricsPanel from "./MetricsPanel";
import WeightsGrid, { type HeadEdit } from "./WeightsGrid";

const SOURCES: ExampleSource[] = ["human", "agent", "generated", "production"];
const BATCH = 12;

type StepState = "done" | "todo" | "blocked";

function Step({ n, title, state, summary, children }: { n: number; title: string; state: StepState; summary?: ReactNode; children: ReactNode }) {
  return (
    <li className="relative grid grid-cols-[1.75rem_minmax(0,1fr)] gap-3">
      <div className="flex flex-col items-center">
        <span
          className={cn(
            "flex h-6 w-6 items-center justify-center rounded-full border font-mono text-[11px]",
            state === "done" && "border-emerald-500/40 bg-emerald-500/10 text-emerald-700 dark:text-emerald-400",
            state === "todo" && "border-brand-400 bg-brand-500/10 text-brand-600",
            state === "blocked" && "border-border text-muted-foreground",
          )}
          aria-label={state === "done" ? "Done" : state === "todo" ? "Next" : "Waiting"}
        >
          {state === "done" ? <Check className="h-3.5 w-3.5" /> : n}
        </span>
        <span className="mt-1 w-px flex-1 bg-border" />
      </div>
      <section className="min-w-0 pb-6">
        <div className="flex flex-wrap items-baseline gap-x-3 gap-y-0.5">
          <h2 className={cn("m-0 text-[14px] font-semibold", state === "blocked" ? "text-muted-foreground" : "text-foreground")}>{title}</h2>
          {summary && <span className="text-[12px] text-muted-foreground">{summary}</span>}
        </div>
        <div className="mt-2">{children}</div>
      </section>
    </li>
  );
}

export default function TrainTab() {
  const { id, detail, version, reload, examples, goTo } = useIntuition();
  // `ungraded` is what the draft needs before fitting; `toGrade` also includes the
  // active version's answers the promotion gate compares against.
  const ungraded = detail.counts.ungraded;
  const toGrade = detail.counts.ungraded_total;
  const hasRubric = (version?.rubric.length ?? 0) > 0;
  const metrics = version?.metrics ?? null;
  const head = version?.head ?? null;
  const stale = version?.head_stale ?? true;

  // Grading loop
  const [grading, setGrading] = useState(false);
  const [progress, setProgress] = useState<{ done: number; total: number; failed: number; errors: string[] } | null>(null);
  const cancel = useRef(false);

  async function grade() {
    setGrading(true);
    cancel.current = false;
    let done = 0;
    let failed = 0;
    let total = toGrade;
    const errors = new Set<string>();
    setProgress({ done, total, failed, errors: [] });
    try {
      while (!cancel.current) {
        const res = await imGrade(id, BATCH);
        done += res.graded;
        failed += res.failed;
        res.errors.forEach((e) => errors.add(e));
        total = Math.max(total, done + res.remaining);
        setProgress({ done, total, failed, errors: [...errors] });
        if (res.remaining === 0) break;
        if (res.graded === 0) break; // every call in the batch failed; stop rather than spin
      }
      if (failed === 0 && !cancel.current) toast.success(`Graded ${done} item${done === 1 ? "" : "s"}`);
    } catch (e) {
      toast.error(errorMessage(e));
    } finally {
      setGrading(false);
      void reload();
    }
  }

  // Fit controls (defaults from the last fit)
  const last = metrics?.fit_options;
  const [l2, setL2] = useState(String(last?.l2 ?? DEFAULT_L2));
  const [trainOn, setTrainOn] = useState<"train" | "all">(last?.train_on ?? "train");
  const [sources, setSources] = useState<Set<ExampleSource>>(new Set(last?.sources ?? SOURCES));
  const [calibrate, setCalibrate] = useState(last?.calibrate ?? true);
  const [fitting, setFitting] = useState(false);
  const l2Value = Number(l2);
  const l2Bad = !Number.isFinite(l2Value) || l2Value < 0 || l2Value > 100;

  async function fit(options?: { l2: number; train_on: "train" | "all"; sources: ExampleSource[] | null; calibrate: boolean }) {
    setFitting(true);
    try {
      const body = options ?? { l2: l2Value, train_on: trainOn, sources: sources.size === SOURCES.length ? null : [...sources], calibrate };
      const res = await imFit(id, body);
      toast.success(`Fitted · held-out accuracy ${pct(res.metrics.eval.accuracy, 1)} (n=${res.metrics.eval.n})`);
      await reload();
    } catch (e) {
      toast.error(errorMessage(e));
    } finally {
      setFitting(false);
    }
  }

  async function saveHead(edit: HeadEdit) {
    try {
      const res = await imSetHead(id, edit);
      toast.success(`Weights saved · held-out accuracy ${pct(res.metrics.eval.accuracy, 1)}`);
      await reload();
    } catch (e) {
      toast.error(errorMessage(e));
    }
  }

  const fitBlocked = !hasRubric ? "Add rubric questions first" : ungraded > 0 ? `Grade the ${ungraded} remaining item${ungraded === 1 ? "" : "s"} first` : null;
  const gradeState: StepState = !hasRubric ? "blocked" : toGrade === 0 ? "done" : "todo";
  const fitState: StepState = fitBlocked ? "blocked" : head && !stale && metrics ? "done" : "todo";

  return (
    <div className="space-y-4">
      {!hasRubric && (
        <Callout tone="info" action={<Button size="sm" onClick={() => goTo("rubric")}>Write a rubric</Button>}>
          The head learns from the judge’s answers to your rubric questions. Add some questions first.
        </Callout>
      )}
      {!detail.draft && detail.active && (
        <Callout tone="info">Showing active v{detail.active.number}. Fitting or editing weights creates a draft; the active version keeps serving until you promote.</Callout>
      )}
      <ol className="m-0 list-none p-0">
        <Step
          n={1}
          title="Grade"
          state={gradeState}
          summary={hasRubric ? (toGrade === 0 ? "Every example has judge answers for the current rubric." : `${toGrade} item${toGrade === 1 ? "" : "s"} need judge answers${toGrade > ungraded ? " (including answers under the active version, for the promotion comparison)" : ""}.`) : undefined}
        >
          <p className="m-0 mb-2 max-w-2xl text-[12px] leading-relaxed text-muted-foreground">
            Asks Jev each rubric question about each example. Answers are cached per question, so only new or changed questions cost a call.
          </p>
          <div className="flex flex-wrap items-center gap-3">
            {grading ? (
              <Button variant="outline" size="sm" onClick={() => (cancel.current = true)}>
                <Square /> Stop
              </Button>
            ) : (
              <Button size="sm" variant={toGrade ? "default" : "outline"} onClick={() => void grade()} disabled={!hasRubric || toGrade === 0 || !detail.judge.configured} title={!detail.judge.configured ? "Set TYPESAFE_API_KEY to grade" : undefined}>
                <Play /> Grade now
              </Button>
            )}
            {progress && (
              <div className="flex min-w-60 flex-1 items-center gap-2.5">
                <Bar value={progress.total ? progress.done / progress.total : 1} tone="brand" className="h-2 max-w-sm" />
                <span className="font-mono text-[11.5px] text-muted-foreground tabular-nums">
                  {progress.done}/{progress.total}
                  {progress.failed > 0 && <span className="text-red-600 dark:text-red-400"> · {progress.failed} failed</span>}
                </span>
                {grading && <Spinner />}
              </div>
            )}
          </div>
          {progress && progress.errors.length > 0 && (
            <div className="mt-2">
              <Callout tone="danger">
                <ul className="m-0 list-none space-y-0.5 p-0 font-mono text-[11.5px]">
                  {progress.errors.map((e) => (
                    <li key={e}>{e}</li>
                  ))}
                </ul>
              </Callout>
            </div>
          )}
        </Step>

        <Step n={2} title="Fit" state={fitState} summary={fitBlocked ?? (stale ? "The head doesn’t match the rubric and labels yet." : last ? `Last fit on ${last.rows} rows.` : undefined)}>
          {stale && head && hasRubric && (
            <div className="mb-2">
              <Callout tone="warning">Rubric or labels changed since the last fit — fit to rebuild the head.</Callout>
            </div>
          )}
          <form
            className="flex flex-wrap items-end gap-x-5 gap-y-3"
            onSubmit={(e) => {
              e.preventDefault();
              void fit();
            }}
          >
            <label className="block">
              <span className="mb-1 block text-[11.5px] font-medium text-dim">L2 regularization</span>
              <input value={l2} onChange={(e) => setL2(e.target.value)} inputMode="decimal" aria-invalid={l2Bad || undefined} className={cn(inputClass, "h-7 w-24 py-0 font-mono text-[12px]", l2Bad && "border-red-500/60")} />
            </label>
            <fieldset className="m-0 border-0 p-0">
              <legend className="mb-1 text-[11.5px] font-medium text-dim">Train on</legend>
              <div className="flex gap-3 text-[12px]">
                {(["train", "all"] as const).map((v) => (
                  <label key={v} className="inline-flex items-center gap-1.5">
                    <input type="radio" name="train_on" checked={trainOn === v} onChange={() => setTrainOn(v)} className="accent-brand-500" />
                    {v === "train" ? "Train split" : "All data"}
                  </label>
                ))}
              </div>
            </fieldset>
            <fieldset className="m-0 border-0 p-0">
              <legend className="mb-1 text-[11.5px] font-medium text-dim">Sources</legend>
              <div className="flex flex-wrap gap-3 text-[12px]">
                {SOURCES.map((s) => (
                  <label key={s} className="inline-flex items-center gap-1.5">
                    <input
                      type="checkbox"
                      checked={sources.has(s)}
                      onChange={(e) =>
                        setSources((prev) => {
                          const next = new Set(prev);
                          if (e.target.checked) next.add(s);
                          else next.delete(s);
                          return next;
                        })
                      }
                      className="accent-brand-500"
                    />
                    {s}
                  </label>
                ))}
              </div>
            </fieldset>
            <label className="inline-flex items-center gap-1.5 text-[12px]" title="Fit a temperature on out-of-fold predictions so confidences mean what they say">
              <input type="checkbox" checked={calibrate} onChange={(e) => setCalibrate(e.target.checked)} className="accent-brand-500" />
              Calibrate
            </label>
            <Button type="submit" size="sm" disabled={fitting || fitBlocked !== null || l2Bad || sources.size === 0} title={fitBlocked ?? undefined}>
              {fitting && <Spinner />}
              Fit head
            </Button>
          </form>
          <p className="m-0 mt-2 max-w-2xl text-[11.5px] leading-relaxed text-muted-foreground">
            L2 pulls weights toward zero: raise it (e.g. 0.05) when you have few examples or the head overfits; lower it when you have plenty. “All data” also trains on held-out examples, so held-out metrics stop being an honest estimate.
          </p>
        </Step>

        <Step n={3} title="Metrics" state={metrics ? "done" : "blocked"} summary={metrics ? `Held-out accuracy ${pct(metrics.eval.accuracy, 1)} on ${metrics.eval.n}` : "Fit to evaluate."}>
          {metrics ? (
            <MetricsPanel
              metrics={metrics}
              outputType={detail.model.output_type}
              classes={version?.classes ?? []}
              examples={examples}
              onOpenExample={(exampleId) => goTo("examples", { example: exampleId })}
            />
          ) : (
            <p className="m-0 text-[12px] text-muted-foreground">Metrics appear after the first fit.</p>
          )}
        </Step>

        <Step n={4} title="Weights" state={head && !stale ? "done" : "blocked"} summary={head?.edited ? <span className="tag tag-warning">hand-edited</span> : head?.fit ? `${head.fit.converged ? "converged" : "did not converge"} in ${head.fit.iterations} iterations` : undefined}>
          {head && !stale && version ? (
            <WeightsGrid
              key={JSON.stringify([head.weights, head.bias, head.temperature])}
              head={head}
              rubric={version.rubric}
              onSave={saveHead}
              refitting={fitting}
              onRefit={() => void fit(last ? { l2: last.l2, train_on: last.train_on, sources: last.sources, calibrate: last.calibrate } : undefined)}
            />
          ) : (
            <p className="m-0 text-[12px] text-muted-foreground">{stale && head ? "Rubric or labels changed — fit to rebuild the head." : "Weights appear after the first fit."}</p>
          )}
        </Step>
      </ol>
    </div>
  );
}
