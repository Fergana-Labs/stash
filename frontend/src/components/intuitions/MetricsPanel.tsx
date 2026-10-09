"use client";

import { cn } from "@/lib/utils";
import type { Example, Metrics, OutputType } from "@/lib/intuition-api";
import { itemSummary, labelText, num, pct } from "./im-helpers";
import { Metric, MetricGrid, Panel } from "./im-ui";
import ReliabilityChart from "./ReliabilityChart";

export function ConfusionMatrix({ confusion, classes }: { confusion: Record<string, Record<string, number>>; classes: string[] }) {
  const max = Math.max(1, ...classes.flatMap((a) => classes.map((p) => confusion[a]?.[p] ?? 0)));
  return (
    <div className="overflow-x-auto">
      <table className="border-collapse text-[11.5px]">
        <thead>
          <tr>
            <th className="px-2 py-1 text-left text-[10.5px] font-normal text-muted-foreground">label ↓ / predicted →</th>
            {classes.map((c) => (
              <th key={c} className="px-2 py-1 text-center font-mono font-medium text-dim">
                {c}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {classes.map((actual) => (
            <tr key={actual}>
              <th className="px-2 py-1 text-left font-mono font-medium text-dim">{actual}</th>
              {classes.map((predicted) => {
                const n = confusion[actual]?.[predicted] ?? 0;
                const right = actual === predicted;
                return (
                  <td
                    key={predicted}
                    className={cn("h-8 min-w-12 border border-border-subtle px-2 text-center font-mono tabular-nums", n === 0 ? "text-muted-foreground/60" : "text-foreground")}
                    style={{ background: n ? (right ? `rgba(34,197,94,${(0.08 + 0.3 * (n / max)).toFixed(3)})` : `rgba(239,68,68,${(0.06 + 0.3 * (n / max)).toFixed(3)})`) : undefined }}
                  >
                    {n}
                  </td>
                );
              })}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

/** Held-out and train metrics of a version, plus where it goes wrong. */
export default function MetricsPanel({
  metrics,
  outputType,
  classes,
  examples,
  onOpenExample,
}: {
  metrics: Metrics;
  outputType: OutputType;
  classes: string[];
  examples: Example[] | null;
  onOpenExample: (id: string) => void;
}) {
  const { eval: held, train } = metrics;
  const byId = new Map((examples ?? []).map((e) => [e.id, e]));
  const mistakes = held.rows.filter((r) => r.predicted !== r.label).sort((a, b) => a.p_true - b.p_true);
  const opts = metrics.fit_options;

  return (
    <div className="space-y-3">
      <MetricGrid>
        <Metric label="Held-out accuracy" value={pct(held.accuracy, 1)} hint={`n = ${held.n}`} emphasis />
        <Metric label="Log loss" value={num(held.log_loss)} hint="held-out, lower is better" />
        <Metric label="ECE" value={num(held.ece)} hint="calibration error" />
        <Metric label="Train accuracy" value={pct(train.accuracy, 1)} hint={`n = ${train.n}`} />
      </MetricGrid>
      {opts && (
        <p className="m-0 font-mono text-[11px] text-muted-foreground">
          fit on {opts.rows} rows · {opts.train_on === "all" ? "all data" : "train split"} · l2 {opts.l2} · {opts.sources ? opts.sources.join("+") : "all sources"}
          {opts.calibrate ? " · calibrated" : ""}
        </p>
      )}
      {held.n === 0 ? (
        <p className="m-0 text-[12.5px] text-muted-foreground">No held-out examples are graded yet, so there’s nothing to measure generalization on. Move some labeled examples to held-out.</p>
      ) : (
        <div className="grid gap-3 lg:grid-cols-2">
          {outputType === "choice" && held.confusion && (
            <Panel title="Confusion (held-out)">
              <ConfusionMatrix confusion={held.confusion} classes={classes} />
            </Panel>
          )}
          {held.reliability && held.reliability.length > 0 && (
            <Panel title="Reliability (held-out)">
              <ReliabilityChart bins={held.reliability} />
            </Panel>
          )}
        </div>
      )}
      {mistakes.length > 0 && (
        <Panel title={`Held-out mistakes · ${mistakes.length}`} description="Most confidently wrong first. Open one to relabel it, or use it to write a sharper question.">
          <ul className="m-0 -my-1 list-none divide-y divide-border-subtle p-0">
            {mistakes.slice(0, 12).map((r) => {
              const e = byId.get(r.example_id);
              const kind = e?.kind ?? "item";
              return (
                <li key={r.example_id}>
                  <button type="button" onClick={() => onOpenExample(r.example_id)} className="flex w-full items-center gap-3 py-1.5 text-left hover:bg-muted/40">
                    <span className="min-w-0 flex-1 truncate text-[12px] text-foreground">{e ? itemSummary(e.item) : r.example_id}</span>
                    <span className="shrink-0 font-mono text-[11.5px]">
                      <span className="text-emerald-700 dark:text-emerald-400">{labelText(r.label, kind)}</span>
                      <span className="text-muted-foreground"> → </span>
                      <span className="text-red-600 dark:text-red-400">{labelText(r.predicted, kind)}</span>
                    </span>
                    <span className="w-16 shrink-0 text-right font-mono text-[11px] text-muted-foreground" title="Probability the head gave the true label">
                      p {pct(r.p_true)}
                    </span>
                  </button>
                </li>
              );
            })}
          </ul>
        </Panel>
      )}
    </div>
  );
}
