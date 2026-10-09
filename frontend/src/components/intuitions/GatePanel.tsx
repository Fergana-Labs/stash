"use client";

import { CheckCircle2, XCircle } from "lucide-react";
import { cn } from "@/lib/utils";
import type { Gate, Metrics } from "@/lib/intuition-api";
import { num, pct } from "./im-helpers";

const CHECK_NAMES: Record<string, string> = {
  held_out_size: "Enough held-out examples",
  accuracy_not_lower: "Accuracy not lower than active",
  log_loss_within_slack: "Log loss within +0.02 of active",
  incumbent_graded: "Active version graded on held-out",
};

/** Promotion checks plus draft-vs-active held-out comparison. */
export default function GatePanel({ gate, metrics }: { gate: Gate; metrics: Metrics | null }) {
  const draft = metrics?.eval;
  const active = gate.incumbent;
  const rows: { label: string; d: string; a: string; better: boolean | null }[] = [
    { label: "Held-out n", d: String(draft?.n ?? "—"), a: String(active?.n ?? "—"), better: null },
    { label: "Accuracy", d: pct(draft?.accuracy, 1), a: pct(active?.accuracy, 1), better: cmp(draft?.accuracy, active?.accuracy, true) },
    { label: "Log loss", d: num(draft?.log_loss), a: num(active?.log_loss), better: cmp(draft?.log_loss, active?.log_loss, false) },
    { label: "ECE", d: num(draft?.ece), a: num(active?.ece), better: cmp(draft?.ece, active?.ece, false) },
  ];
  return (
    <div className="grid gap-4 md:grid-cols-2">
      <ul className="m-0 list-none space-y-1.5 p-0">
        {gate.checks.map((c) => (
          <li key={c.name} className="flex items-start gap-2">
            {c.passed ? <CheckCircle2 className="mt-px h-4 w-4 shrink-0 text-emerald-600" aria-label="Passed" /> : <XCircle className="mt-px h-4 w-4 shrink-0 text-red-500" aria-label="Failed" />}
            <div className="min-w-0">
              <div className="text-[12.5px] text-foreground">{CHECK_NAMES[c.name] ?? c.name.replaceAll("_", " ")}</div>
              <div className="font-mono text-[11px] text-muted-foreground">{c.detail}</div>
            </div>
          </li>
        ))}
        {active === null && <li className="text-[12px] text-muted-foreground">No comparable active version, so only the size check applies.</li>}
      </ul>
      <table className="w-full border-collapse self-start text-[12px]">
        <thead>
          <tr className="text-[10.5px] tracking-wide text-muted-foreground uppercase">
            <th className="py-1 text-left font-medium">Held-out</th>
            <th className="py-1 text-right font-medium">Draft</th>
            <th className="py-1 text-right font-medium">Active{gate.active_version != null ? ` v${gate.active_version}` : ""}</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.label} className="border-t border-border-subtle">
              <td className="py-1 text-dim">{r.label}</td>
              <td className={cn("py-1 text-right font-mono tabular-nums", r.better === true && "text-emerald-700 dark:text-emerald-400", r.better === false && "text-red-600 dark:text-red-400")}>{r.d}</td>
              <td className="py-1 text-right font-mono text-muted-foreground tabular-nums">{r.a}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function cmp(d: number | null | undefined, a: number | null | undefined, higherIsBetter: boolean): boolean | null {
  if (d == null || a == null || Math.abs(d - a) < 1e-9) return null;
  return higherIsBetter ? d > a : d < a;
}
