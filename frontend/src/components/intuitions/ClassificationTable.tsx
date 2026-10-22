"use client";

import type { Classification, EvalRow } from "@/lib/intuition-api";
import { humanize } from "@/lib/behaviors-api";

const fmt = (v: number | null | undefined) => (v == null ? "—" : v.toFixed(2));

/** Per-class precision/recall/F1, macro F1 and Cohen's kappa from held-out rows (mirrors head.classification). */
export function classificationFromRows(rows: Pick<EvalRow, "label" | "predicted">[], classes?: string[]): Classification | null {
  if (!rows.length) return null;
  const labels = classes?.length ? classes : [...new Set(rows.flatMap((r) => [r.label, r.predicted]))].sort();
  const per_class: Classification["per_class"] = {};
  for (const c of labels) {
    const tp = rows.filter((r) => r.label === c && r.predicted === c).length;
    const fp = rows.filter((r) => r.label !== c && r.predicted === c).length;
    const fn = rows.filter((r) => r.label === c && r.predicted !== c).length;
    const precision = tp + fp ? tp / (tp + fp) : null;
    const recall = tp + fn ? tp / (tp + fn) : null;
    const f1 = precision !== null && recall !== null ? (precision + recall ? (2 * precision * recall) / (precision + recall) : 0) : null;
    per_class[c] = { precision, recall, f1, support: tp + fn };
  }
  const scored = Object.values(per_class).filter((v) => v.f1 !== null && v.support).map((v) => v.f1!);
  const n = rows.length;
  const observed = rows.filter((r) => r.label === r.predicted).length / n;
  const expected = labels.reduce((s, c) => s + (rows.filter((r) => r.label === c).length / n) * (rows.filter((r) => r.predicted === c).length / n), 0);
  return {
    per_class,
    macro_f1: scored.length ? scored.reduce((a, b) => a + b, 0) / scored.length : null,
    kappa: expected === 1 ? 1 : (observed - expected) / (1 - expected),
  };
}

export default function ClassificationTable({ classification }: { classification: Classification }) {
  const entries = Object.entries(classification.per_class);
  return (
    <div className="space-y-1.5">
      <p className="m-0 text-[12px]">
        Macro F1 <b className="font-mono tabular-nums">{fmt(classification.macro_f1)}</b>
        
        <span title="Agreement beyond chance (Cohen's kappa)">κ <b className="font-mono tabular-nums">{fmt(classification.kappa)}</b></span>
      </p>
      <div className="overflow-x-auto">
        <table aria-label="Per-class metrics" className="w-full border-collapse text-[11.5px]">
          <thead><tr className="text-left text-[10.5px] text-muted-foreground"><th className="py-1 pr-2 font-normal">Label</th><th className="px-2 py-1 text-right font-normal">Precision</th><th className="px-2 py-1 text-right font-normal">Recall</th><th className="px-2 py-1 text-right font-normal">F1</th><th className="py-1 pl-2 text-right font-normal">Support</th></tr></thead>
          <tbody>
            {entries.map(([label, m]) => (
              <tr key={label} className="border-t border-border-subtle">
                <td className="py-1 pr-2 text-dim" title={label}>{humanize(label)}</td>
                <td className="px-2 py-1 text-right font-mono tabular-nums">{fmt(m.precision)}</td>
                <td className="px-2 py-1 text-right font-mono tabular-nums">{fmt(m.recall)}</td>
                <td className="px-2 py-1 text-right font-mono tabular-nums">{fmt(m.f1)}</td>
                <td className="py-1 pl-2 text-right font-mono tabular-nums text-muted-foreground">{m.support}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
