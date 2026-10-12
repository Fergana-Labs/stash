"use client";

import { useState, type ReactNode } from "react";
import { Play } from "lucide-react";
import { Button } from "@/components/ui/button";
import { errorMessage } from "@/components/reward-models/rm-text";
import { cn } from "@/lib/utils";
import { imCompare, imPredict, type Comparison, type Item, type Prediction, type Version } from "@/lib/intuition-api";
import { pct, signed } from "./im-helpers";
import { Bar, Callout, Segmented, Spinner, useIntuition } from "./im-ui";
import { ContributionBars, ProbabilityBars, RubricAnswersView } from "./ProbabilityBars";
import TraceSandboxInput from "@/components/reward-models/TraceSandboxInput";
import AgentUsagePanel from "./AgentUsagePanel";

type Which = "active" | "draft";
type Mode = "item" | "pair";

function servable(v: Version | null): boolean {
  return !!v && !!v.head && !v.head_stale;
}

function hasTrace(item: Item | null): item is Item {
  return item !== null && (typeof item !== "string" || item.trim().length > 0);
}

export default function PlaygroundTab() {
  const { id, detail } = useIntuition();
  const outputType = detail.model.output_type;
  const canActive = servable(detail.active);
  const canDraft = servable(detail.draft);
  const [which, setWhich] = useState<Which>(canActive || !canDraft ? "active" : "draft");
  const [mode, setMode] = useState<Mode>(outputType === "preference" ? "pair" : "item");
  const [a, setA] = useState<Item | null>(null);
  const [b, setB] = useState<Item | null>(null);
  const [running, setRunning] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [prediction, setPrediction] = useState<Prediction | null>(null);
  const [comparison, setComparison] = useState<Comparison | null>(null);
  const version = which === "draft" ? detail.draft : detail.active;
  const rubric = version?.rubric ?? [];
  const labels = version?.labels ?? [];

  function clearResult() {
    setPrediction(null); setComparison(null); setError(null);
  }

  async function run() {
    if (running || !servable(version) || !hasTrace(a) || (mode === "pair" && !hasTrace(b))) return;
    setRunning(true);
    setError(null);
    try {
      if (mode === "pair" && hasTrace(b)) {
        setComparison(await imCompare(id, a, b, which));
        setPrediction(null);
      } else {
        setPrediction(await imPredict(id, a, which));
        setComparison(null);
      }
    } catch (e) {
      setError(errorMessage(e));
    } finally {
      setRunning(false);
    }
  }

  return (
    <div className="space-y-4">
      <div className="grid border-b border-border lg:grid-cols-2 lg:divide-x lg:divide-border">
        <Panel
          title="Input"
          actions={
            <>
              {outputType === "preference" && (
                <Segmented
                  size="xs"
                  ariaLabel="Input mode"
                  value={mode}
                  onChange={(m) => {
                    if (running) return;
                    setMode(m);
                    setPrediction(null);
                    setComparison(null);
                  }}
                  options={[
                    { value: "pair", label: "Compare A/B" },
                    { value: "item", label: "Score one" },
                  ]}
                />
              )}
              {(canActive || canDraft) && <Segmented
                size="xs"
                ariaLabel="Version"
                value={which}
                onChange={setWhich}
                options={[
                  ...(canActive ? [{ value: "active" as const, label: `Active v${detail.active?.number}` }] : []),
                  ...(canDraft ? [{ value: "draft" as const, label: `Draft v${detail.draft?.number}` }] : []),
                ]}
              />}
            </>
          }
        >
          <form
            className="space-y-3"
            onSubmit={(e) => {
              e.preventDefault();
              void run();
            }}
          >
            <TraceSandboxInput disabled={running} label={mode === "pair" ? "Trace A" : "Trace"} onChange={(item) => { setA(item); clearResult(); }} />
            {mode === "pair" && <TraceSandboxInput disabled={running} label="Trace B" onChange={(item) => { setB(item); clearResult(); }} />}
            <div className="flex items-center gap-2">
              <Button size="sm" type="submit" disabled={running || !servable(version) || !hasTrace(a) || (mode === "pair" && !hasTrace(b))}>
                {running ? <Spinner /> : <Play />}
                {mode === "pair" ? "Compare" : "Run"}
              </Button>
              <span className="text-[11.5px] text-muted-foreground">⌘↵</span>
            </div>
            {error && <Callout tone="danger">{error}</Callout>}
          </form>
        </Panel>

        {prediction ? (
          <PredictionResult
            prediction={prediction}
            labelOrder={outputType === "choice" ? labels.map((l) => l.id) : ["good", "bad"]}
            describe={(l) => labels.find((x) => x.id === l)?.description}
          />
        ) : comparison ? (
          <ComparisonResult comparison={comparison} />
        ) : (
          <section className="border-t border-border px-5 py-3 lg:border-t-0" aria-label="Model output">
            <h2 className="m-0 text-[13px] font-semibold">Output</h2>
            <div className="mt-5 text-[12px] text-muted-foreground">{running ? <span role="status" className="flex items-center gap-2"><Spinner />Evaluating…</span> : "Run an input to see the model’s prediction."}</div>
          </section>
        )}
      </div>

      {(prediction || comparison) && (
        <div className="grid gap-4 lg:grid-cols-2">
          <Panel title="Rubric answers" description={comparison ? "Top bar A, bottom bar B." : "What the judge answered for each question."}>
            <RubricAnswersView rubric={rubric} answers={prediction?.rubric ?? comparison!.rubric_a} compareWith={comparison?.rubric_b} />
          </Panel>
          <Panel
            title="Decision details"
            description={
              comparison
                ? "How the rubric answers affect the comparison."
                : outputType === "choice"
                  ? `How the rubric answers affect “${prediction!.label}”.`
                  : "How the rubric answers affect the score."
            }
          >
            <ContributionBars rubric={rubric} contributions={comparison ? comparison.contributions : prediction!.contributions[outputType === "choice" ? prediction!.label : "score"]} />
          </Panel>
        </div>
      )}

      <AgentUsagePanel modelId={id} outputType={outputType} sample={hasTrace(a) ? a : "…"} />
    </div>
  );
}

function PredictionResult({
  prediction,
  labelOrder,
  describe,
}: {
  prediction: Prediction;
  labelOrder: string[];
  describe: (label: string) => string | undefined;
}) {
  const description = describe(prediction.label);
  return (
    <Panel title="Output" actions={<span className="font-mono text-[11.5px] text-muted-foreground">v{prediction.version}</span>}>
      <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
        <span className="font-mono text-[22px] font-semibold text-foreground">{prediction.label}</span>
        <span className="text-[12.5px] text-muted-foreground">
          <span className="font-mono text-foreground">{pct(prediction.confidence)}</span> confident
        </span>
        {prediction.score != null && <span className="font-mono text-[12px] text-muted-foreground">score {signed(prediction.score, 3)}</span>}
      </div>
      {description && <p className="m-0 mt-1 text-[12.5px] text-muted-foreground">{description}</p>}
      <div className="mt-3">
        <ProbabilityBars probabilities={prediction.probabilities} order={labelOrder.filter((l) => l in prediction.probabilities)} highlight={prediction.label} describe={describe} />
      </div>
    </Panel>
  );
}

function ComparisonResult({ comparison }: { comparison: Comparison }) {
  const winner = comparison.winner === "a" ? "A" : "B";
  return (
    <Panel title="Comparison" actions={<span className="font-mono text-[11.5px] text-muted-foreground">v{comparison.version}</span>}>
      <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
        <span className="text-[22px] font-semibold text-foreground">{winner} is better</span>
        <span className="text-[12.5px] text-muted-foreground">
          <span className="font-mono text-foreground">{pct(comparison.confidence)}</span> confident
        </span>
      </div>
      <div className="mt-3 space-y-2">
        <div className="grid grid-cols-[5rem_1fr_3rem] items-center gap-2.5">
          <span className="text-[12px] text-dim">P(A wins)</span>
          <Bar value={comparison.p_a_wins} tone="brand" className="h-2" />
          <span className="text-right font-mono text-[11.5px] tabular-nums text-muted-foreground">{pct(comparison.p_a_wins)}</span>
        </div>
        <div className="grid grid-cols-2 gap-px overflow-hidden rounded-md border border-border-subtle bg-border-subtle">
          {(["a", "b"] as const).map((side) => (
            <div key={side} className={cn("bg-surface/60 px-3 py-2", comparison.winner === side && "bg-brand-500/8")}>
              <div className="text-[10.5px] tracking-wide text-muted-foreground uppercase">Score {side.toUpperCase()}</div>
              <div className="font-mono text-[14px] text-foreground tabular-nums">{signed(side === "a" ? comparison.score_a : comparison.score_b, 3)}</div>
            </div>
          ))}
        </div>
      </div>
      <p className="m-0 mt-2 text-[11.5px] text-muted-foreground">Scores are on a logit scale; only the difference between them matters.</p>
    </Panel>
  );
}


/** Flat workspace sections keep the input, result, and diagnostics on one canvas. */
function Panel({ title, description, actions, children }: { title?: string; description?: string; actions?: ReactNode; children?: ReactNode }) {
  return <section className="min-w-0 px-5 py-3">
    <header className="mb-4 flex flex-wrap items-center justify-between gap-2">
      <div><h2 className="m-0 text-[13px] font-semibold">{title}</h2>{description && <p className="mb-0 mt-1 text-[12px] text-muted-foreground">{description}</p>}</div>
      {actions && <div className="flex items-center gap-2">{actions}</div>}
    </header>
    {children}
  </section>;
}
