"use client";

import { Fragment, useMemo, useState } from "react";
import { RotateCcw } from "lucide-react";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import type { Head, RubricQuestion } from "@/lib/intuition-api";
import { describeFeature, groupFeatures, weightColor } from "./im-helpers";
import { Spinner } from "./im-ui";

export interface HeadEdit {
  weights: number[][];
  bias: number[];
  temperature: number;
}

/** Text the user is typing per cell; parsed on save so "-" and "0." are allowed mid-edit. */
type Cells = { weights: string[][]; bias: string[]; temperature: string };

const fmt = (v: number) => String(Number(v.toFixed(4)));

function toCells(head: Head): Cells {
  return { weights: head.weights.map((row) => row.map(fmt)), bias: head.bias.map(fmt), temperature: fmt(head.temperature) };
}

function parse(cells: Cells): HeadEdit | null {
  const n = (s: string) => (s.trim() === "" ? NaN : Number(s));
  const weights = cells.weights.map((row) => row.map(n));
  const bias = cells.bias.map(n);
  const temperature = n(cells.temperature);
  const ok = [...weights.flat(), ...bias, temperature].every(Number.isFinite) && temperature >= 0.01 && temperature <= 100;
  return ok ? { weights, bias, temperature } : null;
}

/**
 * Editable head: rows are features grouped by question, columns are classes.
 * Cell color is a subtle diverging scale (green raises the class's logit, red lowers it).
 */
export default function WeightsGrid({
  head,
  rubric,
  onSave,
  onRefit,
  refitting,
}: {
  head: Head;
  rubric: RubricQuestion[];
  onSave: (edit: HeadEdit) => Promise<void>;
  onRefit: () => void;
  refitting: boolean;
}) {
  const [cells, setCells] = useState<Cells>(() => toCells(head));
  const [saving, setSaving] = useState(false);
  const groups = useMemo(() => groupFeatures(head.feature_names, rubric), [head.feature_names, rubric]);
  const parsed = parse(cells);
  const dirty = JSON.stringify(cells) !== JSON.stringify(toCells(head));
  const maxAbs = Math.max(1e-9, ...head.weights.flat().map(Math.abs), ...(parsed ? parsed.weights.flat().map(Math.abs) : []));
  const preference = head.classes.length === 1 && head.classes[0] === "score";

  const setWeight = (c: number, f: number, text: string) => setCells((s) => ({ ...s, weights: s.weights.map((row, i) => (i === c ? row.map((v, j) => (j === f ? text : v)) : row)) }));
  const cellInput = (value: string, onChange: (text: string) => void, label: string, color?: string) => (
    <input
      type="text"
      inputMode="decimal"
      aria-label={label}
      value={value}
      onChange={(e) => onChange(e.target.value)}
      style={{ background: color }}
      className={cn(
        "h-7 w-full min-w-16 rounded border border-transparent px-1.5 text-right font-mono text-[12px] tabular-nums text-foreground outline-none hover:border-border focus:border-brand-400 focus:ring-2 focus:ring-brand-400/20",
        !Number.isFinite(Number(value)) || value.trim() === "" ? "border-red-500/60" : "",
      )}
    />
  );

  return (
    <div className="space-y-3">
      <div className="overflow-x-auto rounded-md border border-border-subtle">
        <table className="w-full border-collapse text-[12px]">
          <thead className="bg-surface/60">
            <tr>
              <th className="px-3 py-1.5 text-left text-[10.5px] font-medium tracking-wide text-muted-foreground uppercase">Feature</th>
              {head.classes.map((c) => (
                <th key={c} className="w-24 px-1.5 py-1.5 text-right font-mono text-[11.5px] font-medium text-dim">
                  {preference ? "weight" : c}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {groups.map((g) => {
              const single = g.features.length === 1 && g.features[0].info.option === null;
              return (
                <Fragment key={g.questionId}>
                  {!single && (
                    <tr className="border-t border-border-subtle">
                      <td colSpan={head.classes.length + 1} className="px-3 pt-2 pb-0.5">
                        <span className="text-[12px] font-medium text-foreground">{g.question?.prompt ?? g.questionId}</span>
                        <span className="ml-2 font-mono text-[10.5px] text-muted-foreground">{g.questionId}</span>
                      </td>
                    </tr>
                  )}
                  {g.features.map(({ index, info }) => (
                    <tr key={info.feature} className={cn(single && "border-t border-border-subtle")}>
                      <td className={cn("max-w-0 px-3 py-0.5", !single && "pl-6")}>
                        <div className="truncate text-[12px] text-foreground" title={single ? g.question?.prompt : info.optionLabel}>
                          {single ? (g.question?.prompt ?? info.questionId) : info.optionLabel}
                          {single && <span className="text-muted-foreground"> → yes</span>}
                        </div>
                        <div className="truncate font-mono text-[10.5px] text-muted-foreground">{info.feature}</div>
                      </td>
                      {head.classes.map((c, ci) => (
                        <td key={c} className="px-1 py-0.5">
                          {cellInput(cells.weights[ci][index], (t) => setWeight(ci, index, t), `${info.feature} weight for ${c}`, weightColor(Number(cells.weights[ci][index]), maxAbs))}
                        </td>
                      ))}
                    </tr>
                  ))}
                </Fragment>
              );
            })}
            <tr className="border-t border-border bg-surface/40">
              <td className="px-3 py-1">
                <div className="text-[12px] font-medium text-foreground">Bias</div>
                <div className="text-[10.5px] text-muted-foreground">baseline logit per class</div>
              </td>
              {head.classes.map((c, ci) => (
                <td key={c} className="px-1 py-1">
                  {cellInput(cells.bias[ci], (t) => setCells((s) => ({ ...s, bias: s.bias.map((v, i) => (i === ci ? t : v)) })), `Bias for ${c}`)}
                </td>
              ))}
            </tr>
          </tbody>
        </table>
      </div>

      <div className="flex flex-wrap items-center gap-3">
        <label className="inline-flex items-center gap-2 text-[12px] text-dim">
          Temperature
          <span className="w-20">{cellInput(cells.temperature, (t) => setCells((s) => ({ ...s, temperature: t })), "Temperature")}</span>
        </label>
        <span className="text-[11.5px] text-muted-foreground">Logits are divided by this; above 1 softens confidence. 0.01–100.</span>
        <span className="flex-1" />
        <Button variant="ghost" size="sm" onClick={onRefit} disabled={refitting || saving} title="Refit with the last fit settings, discarding hand edits">
          {refitting ? <Spinner /> : <RotateCcw />}
          Reset to fitted
        </Button>
        {dirty && (
          <Button variant="outline" size="sm" onClick={() => setCells(toCells(head))} disabled={saving}>
            Undo edits
          </Button>
        )}
        <Button
          size="sm"
          disabled={!dirty || !parsed || saving}
          onClick={async () => {
            if (!parsed) return;
            setSaving(true);
            try {
              await onSave(parsed);
            } finally {
              setSaving(false);
            }
          }}
        >
          {saving && <Spinner />}
          Save weights
        </Button>
      </div>
      {!parsed && <p className="m-0 text-[12px] text-red-600 dark:text-red-400">Every cell needs a finite number, and temperature must be between 0.01 and 100.</p>}
    </div>
  );
}

/** Read-only head table for version snapshots. */
export function HeadTable({ head, rubric }: { head: Head; rubric: RubricQuestion[] }) {
  const maxAbs = Math.max(1e-9, ...head.weights.flat().map(Math.abs));
  const preference = head.classes.length === 1 && head.classes[0] === "score";
  return (
    <div className="overflow-x-auto rounded-md border border-border-subtle">
      <table className="w-full border-collapse text-[12px]">
        <thead className="bg-surface/60">
          <tr>
            <th className="px-3 py-1 text-left text-[10.5px] font-medium tracking-wide text-muted-foreground uppercase">Feature</th>
            {head.classes.map((c) => (
              <th key={c} className="w-20 px-2 py-1 text-right font-mono text-[11px] font-medium text-dim">
                {preference ? "weight" : c}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {head.feature_names.map((name, f) => {
            const info = describeFeature(name, rubric);
            return (
              <tr key={name} className="border-t border-border-subtle">
                <td className="max-w-0 px-3 py-1">
                  <div className="truncate" title={info.question?.prompt}>
                    {info.question?.prompt ?? info.questionId}
                    <span className="text-muted-foreground"> → {info.optionLabel}</span>
                  </div>
                </td>
                {head.classes.map((c, ci) => (
                  <td key={c} className="px-2 py-1 text-right font-mono tabular-nums" style={{ background: weightColor(head.weights[ci][f], maxAbs) }}>
                    {head.weights[ci][f].toFixed(2)}
                  </td>
                ))}
              </tr>
            );
          })}
          <tr className="border-t border-border bg-surface/40">
            <td className="px-3 py-1 font-medium">Bias · temperature {head.temperature.toFixed(2)}</td>
            {head.bias.map((b, ci) => (
              <td key={ci} className="px-2 py-1 text-right font-mono tabular-nums">
                {b.toFixed(2)}
              </td>
            ))}
          </tr>
        </tbody>
      </table>
    </div>
  );
}
