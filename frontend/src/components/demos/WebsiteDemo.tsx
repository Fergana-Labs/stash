"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import {
  ArrowLeft,
  ArrowUpRight,
  Check,
  Code2,
  FileCode2,
  GitBranch,
  Maximize2,
} from "lucide-react";
import { useBreadcrumbs } from "@/components/BreadcrumbContext";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogTitle } from "@/components/ui/dialog";
import { EvalPageFrame } from "@/components/evals/eval-ui";
import { rmGetTrace } from "@/lib/api";
import type { RmTraceDetail } from "@/lib/types";
import { cn } from "@/lib/utils";
import {
  bestWebsiteRevision,
  websiteDemoData,
  type WebsiteRevision,
} from "./website-demo-data";

const stages = ["Trace", "Eval wizard", "Agent run", "Before & after"] as const;
type Stage = (typeof stages)[number];
const pct = (n: number) => `${(n * 100).toFixed(1)}%`;

function Preview({
  revision,
  label,
  onOpen,
}: {
  revision: WebsiteRevision;
  label: string;
  onOpen: (r: WebsiteRevision) => void;
}) {
  return (
    <section className="overflow-hidden rounded-[4px] border border-border bg-background">
      <header className="flex h-10 items-center justify-between border-b border-border px-3 text-xs">
        <span className="font-medium">
          {label}{" "}
          <span className="ml-1.5 font-normal text-muted-foreground">
            v{revision.iteration}
          </span>
        </span>
        <div className="flex items-center gap-3">
          <span
            title="The saved evaluator’s probability of the liked label"
            className="font-mono text-[11px]"
          >
            P(liked) {pct(revision.score)}
          </span>
          <button
            type="button"
            aria-label={`Enlarge ${label.toLowerCase()}`}
            className="cursor-pointer text-muted-foreground hover:text-foreground"
            onClick={() => onOpen(revision)}
          >
            <Maximize2 className="size-3.5" />
          </button>
        </div>
      </header>
      {/* Pixel output from a recorded render; HTML never executes in the app. */}
      {/* eslint-disable-next-line @next/next/no-img-element */}
      <img
        src={revision.image}
        alt={`${label}: rendered Gather landing page, revision ${revision.iteration}`}
        className="block aspect-[3/2] w-full object-cover object-top"
      />
    </section>
  );
}

export default function WebsiteDemo({ traceId }: { traceId: string }) {
  const [trace, setTrace] = useState<RmTraceDetail | null>(null);
  const [error, setError] = useState("");
  const [stage, setStage] = useState<Stage>("Before & after");
  const [selected, setSelected] = useState<number | null>(null);
  const [enlarged, setEnlarged] = useState<WebsiteRevision | null>(null);
  useBreadcrumbs(
    [{ label: "Traces", href: "/reward-models" }, { label: "Website design" }],
    `website-demo-${traceId}`,
  );
  useEffect(() => {
    let cancelled = false;
    rmGetTrace(traceId, true)
      .then((t) => {
        if (!cancelled) setTrace(t);
      })
      .catch((e) => {
        if (!cancelled)
          setError(e instanceof Error ? e.message : "Could not load this demo");
      });
    return () => {
      cancelled = true;
    };
  }, [traceId]);
  const demo = websiteDemoData(trace?.metadata?.website_demo);
  if (!trace)
    return (
      <EvalPageFrame>
        <p role={error ? "alert" : "status"} className="text-sm">
          {error || "Loading website demo…"}
        </p>
      </EvalPageFrame>
    );
  if (!demo)
    return (
      <EvalPageFrame>
        <p role="alert" className="text-sm">
          This trace does not contain a website demo.
        </p>
      </EvalPageFrame>
    );
  const before = demo.artifacts.find((a) => a.iteration === 0)!;
  const best = bestWebsiteRevision(demo.artifacts);
  const candidate =
    demo.artifacts.find((a) => a.iteration === selected) ?? best;
  const evaluation = trace.automatic_evaluation?.current;
  const sourceLink = `/reward-models/traces/${traceId}`;

  return (
    <EvalPageFrame>
      <div className="mx-auto max-w-[1600px]">
        <header className="mb-5 flex flex-wrap items-center justify-between gap-3">
          <div className="flex items-center gap-3">
            <Link
              href="/reward-models"
              aria-label="Back to traces"
              className="text-muted-foreground hover:text-foreground"
            >
              <ArrowLeft className="size-4" />
            </Link>
            <div>
              <p className="mb-1 text-[10px] tracking-[.12em] text-muted-foreground uppercase">
                Website design
              </p>
              <h1 className="text-[22px] leading-tight font-semibold tracking-tight">
                From taste to a better website
              </h1>
            </div>
          </div>
          <div className="flex items-center gap-2">
            <span className="mr-1 text-[11px] text-muted-foreground">
              Recorded agent run · eval v{demo.model_version}
            </span>
            <Button size="xs" variant="outline" asChild>
              <Link href={sourceLink}>
                Open trace <ArrowUpRight />
              </Link>
            </Button>
            <Button size="xs" asChild>
              <Link href={`/reward-models/evals/${demo.model_id}`}>
                Open eval <ArrowUpRight />
              </Link>
            </Button>
          </div>
        </header>
        <nav
          aria-label="Website demo stages"
          className="mb-5 flex gap-1 border-b border-border"
        >
          {stages.map((s, i) => (
            <button
              key={s}
              type="button"
              aria-current={stage === s ? "step" : undefined}
              onClick={() => setStage(s)}
              className={cn(
                "-mb-px flex cursor-pointer items-center gap-2 border-b-2 px-3 py-2.5 text-xs",
                stage === s
                  ? "border-foreground font-medium text-foreground"
                  : "border-transparent text-muted-foreground hover:text-foreground",
              )}
            >
              <span className="text-[10px] opacity-50">0{i + 1}</span>
              {s}
            </button>
          ))}
        </nav>

        {stage === "Trace" && (
          <div className="grid gap-5 lg:grid-cols-[.75fr_1.25fr]">
            <section className="rounded border border-border p-4">
              <div className="mb-4 flex items-center gap-2 text-xs">
                <FileCode2 className="size-4" />
                <b>{demo.file}</b>
                <span className="ml-auto text-muted-foreground">
                  {demo.artifacts.length} revisions
                </span>
              </div>
              <p className="mb-5 text-sm leading-6">
                The agent starts from a real HTML file, renders it, and records
                each edit and evaluation. The same trace keeps the source, tool
                results, completion estimates, and action credits.
              </p>
              <dl className="mb-5 grid grid-cols-2 gap-4 text-xs">
                <div>
                  <dt className="text-muted-foreground">Recorded steps</dt>
                  <dd className="mt-1 text-xl tabular-nums">
                    {trace.steps.length}
                  </dd>
                </div>
                <div>
                  <dt className="text-muted-foreground">Actions credited</dt>
                  <dd className="mt-1 text-xl tabular-nums">
                    {evaluation
                      ? `${evaluation.credited_actions}/${evaluation.total_actions}`
                      : "Pending"}
                  </dd>
                </div>
              </dl>
              <Button size="sm" variant="outline" asChild>
                <Link href={sourceLink}>
                  Inspect the recorded trace <ArrowUpRight />
                </Link>
              </Button>
            </section>
            <Preview
              revision={before}
              label="Starting file"
              onOpen={setEnlarged}
            />
          </div>
        )}

        {stage === "Eval wizard" && (
          <div className="grid items-start gap-5 xl:grid-cols-[1.1fr_.9fr]">
            <section className="rounded border border-border">
              <header className="border-b border-border px-4 py-3">
                <h2 className="text-sm font-medium">The setup conversation</h2>
                <p className="mt-1 text-xs text-muted-foreground">
                  Sample setup · saved eval · {demo.reference_count} visual
                  examples
                </p>
              </header>
              <div className="max-h-[650px] space-y-5 overflow-y-auto p-4">
                {demo.transcript.map((entry, i) => (
                  <div
                    key={i}
                    className={
                      entry.role === "user"
                        ? "ml-12 rounded-[4px] bg-foreground px-3 py-2.5 text-xs leading-5 text-background"
                        : "mr-6 text-xs leading-5 text-foreground"
                    }
                  >
                    {entry.role === "user"
                      ? entry.text
                      : entry.parts.map((p) => p.text).join("\n")}
                  </div>
                ))}
              </div>
            </section>
            <div className="space-y-4">
              <section className="rounded border border-border p-4">
                <div className="mb-3 flex items-center justify-between">
                  <h2 className="text-sm font-medium">What the eval checks</h2>
                  <span className="flex items-center gap-1 text-[11px] text-emerald-700">
                    <Check className="size-3" />
                    Saved
                  </span>
                </div>
                <ul className="space-y-2.5">
                  {demo.criteria.map((q) => (
                    <li key={q.id} className="flex gap-2 text-xs leading-5">
                      <span className="mt-1.5 size-1 shrink-0 rounded-full bg-foreground/40" />
                      {q.prompt}
                    </li>
                  ))}
                </ul>
                <p className="mt-4 border-t border-border pt-3 text-xs text-muted-foreground">
                  Held-out agreement: {pct(demo.agreement)} on {demo.held_out_n}{" "}
                  examples. Small synthetic reference set.
                </p>
              </section>
              <section className="rounded border border-border p-4">
                <h2 className="mb-3 text-sm font-medium">
                  Liked and disliked references
                </h2>
                <div className="grid grid-cols-2 gap-3">
                  {["liked", "disliked"].map((label) => (
                    <div key={label}>
                      <h3 className="mb-2 text-[11px] font-medium capitalize">
                        {label}
                      </h3>
                      <div className="space-y-2">
                        {demo.references
                          .filter((r) => r.label === label)
                          .slice(0, 3)
                          .map((r, i) => (
                            <div
                              key={i}
                              className="overflow-hidden rounded border border-border"
                            >
                              {/* eslint-disable-next-line @next/next/no-img-element */}
                              <img
                                src={r.image}
                                alt={`${label} reference ${i + 1}`}
                                className="aspect-[3/2] w-full object-cover"
                              />
                              <p className="border-t border-border px-2 py-1 text-[10px] text-muted-foreground">
                                {r.split === "eval"
                                  ? "Held out"
                                  : "Training example"}
                              </p>
                            </div>
                          ))}
                      </div>
                    </div>
                  ))}
                </div>
              </section>
            </div>
          </div>
        )}

        {stage === "Agent run" && (
          <div className="grid items-start gap-5 lg:grid-cols-[.65fr_1.35fr]">
            <section className="overflow-hidden rounded border border-border">
              <header className="border-b border-border px-4 py-3">
                <h2 className="flex items-center gap-2 text-sm font-medium">
                  <GitBranch className="size-4" />
                  Eval-guided revisions
                </h2>
                <p className="mt-1 text-xs text-muted-foreground">
                  Generate → render → evaluate → keep the better file
                </p>
              </header>
              <div className="divide-y divide-border">
                {demo.artifacts.map((a) => (
                  <button
                    key={a.iteration}
                    type="button"
                    aria-pressed={candidate.iteration === a.iteration}
                    onClick={() => setSelected(a.iteration)}
                    className={cn(
                      "flex w-full cursor-pointer items-center justify-between gap-3 px-4 py-4 text-left",
                      candidate.iteration === a.iteration
                        ? "bg-surface"
                        : "hover:bg-surface/50",
                    )}
                  >
                    <div>
                      <span className="text-xs font-medium">
                        {a.iteration === 0
                          ? "Initial website"
                          : `Candidate ${a.iteration}`}
                      </span>
                      <p className="mt-1 text-[11px] text-muted-foreground">
                        {a.iteration === 0
                          ? "Baseline"
                          : a.accepted
                            ? "Improved the incumbent"
                            : "Rejected · incumbent retained"}
                        {a.iteration === best.iteration ? " · selected" : ""}
                      </p>
                    </div>
                    <span className="font-mono text-xs">{pct(a.score)}</span>
                  </button>
                ))}
              </div>
              <p className="border-t border-border p-4 text-[11px] leading-5 text-muted-foreground">
                Scores are saved P(liked) predictions from this evaluator. Every
                attempted candidate is kept, including any that scored worse.
              </p>
            </section>
            <div>
              <Preview
                revision={candidate}
                label={
                  candidate.iteration === 0
                    ? "Baseline"
                    : `Candidate ${candidate.iteration}`
                }
                onOpen={setEnlarged}
              />
              <section className="mt-3 rounded border border-border p-3">
                <h3 className="mb-3 text-xs font-medium">Evaluator feedback</h3>
                <div className="space-y-3">
                  {demo.criteria.map((q) => {
                    const value = candidate.rubric[q.id]?.true;
                    return (
                      <div
                        key={q.id}
                        className="flex items-start justify-between gap-4 text-[11px] leading-5"
                      >
                        <span className="text-muted-foreground">
                          {q.prompt}
                        </span>
                        <span className="shrink-0 font-mono">
                          {typeof value === "number" ? pct(value) : "—"}
                        </span>
                      </div>
                    );
                  })}
                </div>
                <p className="mt-3 text-[10px] text-muted-foreground">
                  Judge probability that each criterion is satisfied.
                </p>
              </section>
              <details className="mt-3 rounded border border-border text-xs">
                <summary className="flex cursor-pointer items-center gap-2 px-3 py-2.5">
                  <Code2 className="size-3.5" />
                  Source and prediction receipt
                </summary>
                <div className="space-y-3 border-t border-border p-3">
                  <p className="break-all font-mono text-[10px] text-muted-foreground">
                    Prediction {candidate.prediction_id} · eval v
                    {demo.model_version}
                  </p>
                  <pre className="max-h-80 overflow-auto whitespace-pre-wrap text-[10px] leading-4">
                    {candidate.html}
                  </pre>
                </div>
              </details>
            </div>
          </div>
        )}

        {stage === "Before & after" && (
          <>
            <div className="mb-4 flex flex-wrap items-end justify-between gap-3">
              <div>
                <h2 className="text-base font-medium">
                  Same product. A clearer first impression.
                </h2>
                <p className="mt-1 text-xs text-muted-foreground">
                  The agent revised {demo.file} using the saved eval’s feedback.
                </p>
              </div>
              <div className="text-right">
                <p className="font-mono text-xl tracking-tight">
                  {pct(before.score)}{" "}
                  <span className="text-muted-foreground">→</span>{" "}
                  {pct(best.score)}
                </p>
                <p className="mt-1 text-[10px] text-muted-foreground">
                  P(liked) · selected revision {best.iteration}
                </p>
              </div>
            </div>
            <div className="grid gap-4 lg:grid-cols-2">
              <Preview revision={before} label="Before" onOpen={setEnlarged} />
              <Preview revision={best} label="After" onOpen={setEnlarged} />
            </div>
            <div className="mt-4 flex flex-wrap items-center justify-between gap-3 text-xs">
              <p className="max-w-3xl leading-5 text-muted-foreground">
                Synthetic website examples; actual rendered HTML and saved
                classifier predictions. The score measures this eval’s learned
                preference, rather than universal design quality.
              </p>
              <Button
                size="xs"
                variant="outline"
                onClick={() => setStage("Agent run")}
              >
                Inspect every iteration <ArrowUpRight />
              </Button>
            </div>
          </>
        )}
        <Dialog
          open={!!enlarged}
          onOpenChange={(open) => {
            if (!open) setEnlarged(null);
          }}
        >
          <DialogContent className="max-h-[94vh] overflow-y-auto rounded-[4px] p-3 sm:max-w-[1400px]">
            <DialogTitle className="text-xs">
              Gather · revision {enlarged?.iteration}
            </DialogTitle>
            {enlarged && (
              <>
                {/* eslint-disable-next-line @next/next/no-img-element */}
                <img
                  src={enlarged.image}
                  alt={`Full-size Gather revision ${enlarged.iteration}`}
                  className="w-full"
                />
              </>
            )}
          </DialogContent>
        </Dialog>
      </div>
    </EvalPageFrame>
  );
}
