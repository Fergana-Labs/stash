"use client";

import { useMemo, useState } from "react";
import { Check, Play, Shuffle } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { errorMessage } from "@/components/reward-models/rm-text";
import { cn } from "@/lib/utils";
import { imCompare, imPredict, imReview, type Comparison, type Item, type Prediction, type Version } from "@/lib/intuition-api";
import { detectItemKeys, itemsOf, pct, signed } from "./im-helpers";
import { Bar, Callout, Panel, Segmented, Spinner, useIntuition } from "./im-ui";
import ItemInput, { draftFromItem, draftToItem, emptyDraft, type ItemDraft } from "./ItemInput";
import { ContributionBars, ProbabilityBars, RubricAnswersView } from "./ProbabilityBars";
import AgentUsagePanel from "./AgentUsagePanel";

type Which = "active" | "draft";
type Mode = "item" | "pair";

function servable(v: Version | null): boolean {
  return !!v && !!v.head && !v.head_stale;
}

export default function PlaygroundTab() {
  const { id, detail, examples, goTo, reload, reloadExamples } = useIntuition();
  const outputType = detail.model.output_type;
  const keys = useMemo(() => detectItemKeys(itemsOf(examples ?? [])), [examples]);
  const canActive = servable(detail.active);
  const canDraft = servable(detail.draft);
  const [which, setWhich] = useState<Which>(canActive || !canDraft ? "active" : "draft");
  const [mode, setMode] = useState<Mode>(outputType === "preference" ? "pair" : "item");
  const [a, setA] = useState<ItemDraft>(emptyDraft);
  const [b, setB] = useState<ItemDraft>(emptyDraft);
  const [running, setRunning] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [prediction, setPrediction] = useState<Prediction | null>(null);
  const [comparison, setComparison] = useState<Comparison | null>(null);
  const [reviewed, setReviewed] = useState<string | null>(null);
  const version = which === "draft" ? detail.draft : detail.active;
  const rubric = version?.rubric ?? [];
  const labels = version?.labels ?? [];

  const pool = examples?.filter((e) => e.item_b == null) ?? [];
  function fillRandom() {
    if (pool.length === 0) return;
    const pick = () => pool[Math.floor(Math.random() * pool.length)].item;
    setA(draftFromItem(pick(), keys));
    if (mode === "pair") setB(draftFromItem(pick(), keys));
  }

  async function run() {
    const itemA = draftToItem(a, keys);
    if ("error" in itemA) return setError(mode === "pair" ? `Item A: ${itemA.error}` : itemA.error);
    let itemB: { item: Item } | { error: string } | null = null;
    if (mode === "pair") {
      itemB = draftToItem(b, keys);
      if ("error" in itemB) return setError(`Item B: ${itemB.error}`);
    }
    setRunning(true);
    setError(null);
    setReviewed(null);
    try {
      if (itemB && "item" in itemB) {
        setComparison(await imCompare(id, itemA.item, itemB.item, which));
        setPrediction(null);
      } else {
        setPrediction(await imPredict(id, itemA.item, which));
        setComparison(null);
      }
    } catch (e) {
      setError(errorMessage(e));
    } finally {
      setRunning(false);
    }
  }

  async function review(predictionId: string | null, label: string, shown: string) {
    if (!predictionId) return;
    try {
      await imReview(id, predictionId, { label });
      setReviewed(label);
      toast.success(`Saved as an example labeled “${shown}”`, { action: { label: "View", onClick: () => goTo("examples", { source: "production" }) } });
      void reload();
      void reloadExamples();
    } catch (e) {
      toast.error(errorMessage(e));
    }
  }

  if (!canActive && !canDraft) {
    return (
      <div className="space-y-4">
        <Callout
          tone="info"
          action={
            <Button size="sm" onClick={() => goTo(rubric.length || detail.draft?.rubric.length ? "train" : "rubric")}>
              {rubric.length || detail.draft?.rubric.length ? "Go to Train" : "Write a rubric"}
            </Button>
          }
        >
          Nothing to run yet. A model needs rubric questions and a fitted head before it can judge items: write the rubric, label a few examples, then grade and fit on the Train tab.
        </Callout>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <div className="grid gap-4 lg:grid-cols-[minmax(0,5fr)_minmax(0,6fr)]">
        <Panel
          title="Try it"
          actions={
            <>
              {outputType === "preference" && (
                <Segmented
                  size="xs"
                  ariaLabel="Input mode"
                  value={mode}
                  onChange={(m) => {
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
              <Segmented
                size="xs"
                ariaLabel="Version"
                value={which}
                onChange={setWhich}
                options={[
                  ...(canActive ? [{ value: "active" as const, label: `Active v${detail.active?.number}` }] : []),
                  ...(canDraft ? [{ value: "draft" as const, label: `Draft v${detail.draft?.number}` }] : []),
                ]}
              />
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
            <ItemInput keys={keys} value={a} onChange={setA} label={mode === "pair" ? "Item A" : undefined} disabled={running} onSubmit={() => void run()} />
            {mode === "pair" && <ItemInput keys={keys} value={b} onChange={setB} label="Item B" disabled={running} onSubmit={() => void run()} />}
            <div className="flex items-center gap-2">
              <Button type="submit" disabled={running}>
                {running ? <Spinner /> : <Play />}
                {mode === "pair" ? "Compare" : "Run"}
              </Button>
              <span className="text-[11.5px] text-muted-foreground">⌘↵</span>
              <span className="flex-1" />
              {pool.length > 0 && (
                <Button type="button" variant="ghost" size="sm" onClick={fillRandom} disabled={running}>
                  <Shuffle /> Fill from an example
                </Button>
              )}
            </div>
            {error && <Callout tone="danger">{error}</Callout>}
          </form>
        </Panel>

        {prediction ? (
          <PredictionResult
            prediction={prediction}
            labelOrder={outputType === "choice" ? labels.map((l) => l.id) : ["good", "bad"]}
            describe={(l) => labels.find((x) => x.id === l)?.description}
            reviewed={reviewed}
            onReview={(label) => review(prediction.prediction_id, label, label)}
          />
        ) : comparison ? (
          <ComparisonResult comparison={comparison} reviewed={reviewed} onReview={(label) => review(comparison.prediction_id, label, label === "a" ? "A is better" : "B is better")} />
        ) : (
          <div className="flex min-h-40 items-center justify-center rounded-lg border border-dashed border-border bg-surface/40 px-6 text-center text-[12.5px] text-muted-foreground">
            {running ? <Spinner className="h-4 w-4" /> : "Run an item to see the prediction, the judge’s answers to each question, and why the head decided."}
          </div>
        )}
      </div>

      {(prediction || comparison) && (
        <div className="grid gap-4 lg:grid-cols-2">
          <Panel title="Rubric answers" description={comparison ? "Top bar A, bottom bar B." : "What the judge answered for each question."}>
            <RubricAnswersView rubric={rubric} answers={prediction?.rubric ?? comparison!.rubric_a} compareWith={comparison?.rubric_b} />
          </Panel>
          <Panel
            title="Why"
            description={
              comparison
                ? "Feature contributions to score(A) − score(B). Green favors A."
                : outputType === "choice"
                  ? `Feature contributions to the “${prediction!.label}” logit. Green pushes toward it.`
                  : "Feature contributions to the score. Green raises it."
            }
          >
            <ContributionBars rubric={rubric} contributions={comparison ? comparison.contributions : prediction!.contributions[outputType === "choice" ? prediction!.label : "score"]} />
          </Panel>
        </div>
      )}

      <AgentUsagePanel modelId={id} outputType={outputType} sample={pool[0]?.item ?? (keys ? Object.fromEntries(keys.map((k) => [k, "…"])) : "…")} />
    </div>
  );
}

function ReviewButtons({ options, predicted, reviewed, onReview }: { options: { value: string; label: string }[]; predicted: string; reviewed: string | null; onReview: (value: string) => void | Promise<void> }) {
  const [busy, setBusy] = useState<string | null>(null);
  if (reviewed) {
    const shown = options.find((o) => o.value === reviewed)?.label ?? reviewed;
    return (
      <p className="m-0 inline-flex items-center gap-1.5 text-[12.5px] text-emerald-700 dark:text-emerald-400">
        <Check className="h-3.5 w-3.5" /> Saved as an example: {shown}
      </p>
    );
  }
  return (
    <div className="flex flex-wrap items-center gap-1.5">
      <span className="mr-1 text-[12px] text-dim">Is this right?</span>
      {options.map((o) => (
        <Button
          key={o.value}
          size="xs"
          variant={o.value === predicted ? "secondary" : "outline"}
          disabled={busy !== null}
          onClick={async () => {
            setBusy(o.value);
            await onReview(o.value);
            setBusy(null);
          }}
        >
          {busy === o.value ? <Spinner className="h-3 w-3" /> : o.value === predicted ? <Check /> : null}
          {o.label}
        </Button>
      ))}
    </div>
  );
}

function PredictionResult({
  prediction,
  labelOrder,
  describe,
  reviewed,
  onReview,
}: {
  prediction: Prediction;
  labelOrder: string[];
  describe: (label: string) => string | undefined;
  reviewed: string | null;
  onReview: (label: string) => void | Promise<void>;
}) {
  const description = describe(prediction.label);
  return (
    <Panel title="Prediction" actions={<span className="font-mono text-[11.5px] text-muted-foreground">v{prediction.version}</span>}>
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
      <div className="mt-4 border-t border-border-subtle pt-3">
        {prediction.prediction_id ? (
          <ReviewButtons options={labelOrder.map((l) => ({ value: l, label: l }))} predicted={prediction.label} reviewed={reviewed} onReview={onReview} />
        ) : (
          <p className="m-0 text-[12px] text-muted-foreground">This prediction wasn’t logged, so it can’t be saved as an example.</p>
        )}
      </div>
    </Panel>
  );
}

function ComparisonResult({ comparison, reviewed, onReview }: { comparison: Comparison; reviewed: string | null; onReview: (label: string) => void | Promise<void> }) {
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
      <div className="mt-4 border-t border-border-subtle pt-3">
        {comparison.prediction_id ? (
          <ReviewButtons
            options={[
              { value: "a", label: "A is better" },
              { value: "b", label: "B is better" },
            ]}
            predicted={comparison.winner}
            reviewed={reviewed}
            onReview={onReview}
          />
        ) : (
          <p className="m-0 text-[12px] text-muted-foreground">This comparison wasn’t logged.</p>
        )}
      </div>
      <p className="m-0 mt-2 text-[11.5px] text-muted-foreground">Scores are on a logit scale; only the difference between them matters.</p>
    </Panel>
  );
}
