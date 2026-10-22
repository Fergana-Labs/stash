"use client";

import { useId, useState } from "react";
import { Minus, Plus } from "lucide-react";
import { Button } from "@/components/ui/button";
import { HeadTable } from "@/components/intuitions/WeightsGrid";
import type { Version } from "@/lib/intuition-api";

const number = (value: number | null | undefined) => value == null ? "—" : Number(value.toFixed(4)).toString();

export default function EvalAdvanced({ version, serving }: { version: Version | null; serving: boolean }) {
  const [open, setOpen] = useState(false);
  const panelId = useId();
  const head = version?.head;
  const settings = version?.metrics?.fit_options;
  const values = [
    [serving ? "Serving version" : "Version", version ? `v${version.number}` : "—"],
    ["Judge model", version?.provider_model || "—"],
    ["Training examples", number(head?.fit?.train_rows)],
    ["Held-out examples", number(version?.metrics?.eval.n)],
    ["Probability temperature", number(head?.temperature)],
    ["Regularization (L2)", number(head?.l2)],
    ["Probability calibration", settings ? (settings.calibrate ? "Automatic" : "Off") : "—"],
    ["Judge context examples", number(version?.seed_example_ids?.length)],
  ];
  return <section aria-label="Advanced options" className="overflow-hidden rounded border border-border">
    <Button variant="ghost" className="flex h-auto w-full justify-between rounded-none px-4 py-3 text-left text-xs font-medium" aria-expanded={open} aria-controls={panelId} onClick={() => setOpen(!open)}>Advanced options{open ? <Minus className="size-3.5" /> : <Plus className="size-3.5" />}</Button>
    {open && <div id={panelId} className="space-y-4 border-t border-border p-4">
      <dl className="grid gap-x-8 gap-y-3 text-xs sm:grid-cols-2 lg:grid-cols-4">{values.map(([label, value]) => <div key={label} className="min-w-0 space-y-1"><dt className="text-muted-foreground">{label}</dt><dd className="break-words font-mono text-[11px]">{value}</dd></div>)}</dl>
      {head && version ? <section aria-label="Learned weights" className="space-y-2"><h3 className="text-xs font-medium">Learned weights</h3><HeadTable head={head} rubric={version.rubric} /></section> : <p className="text-xs text-muted-foreground">Calibration details appear after the first update.</p>}
    </div>}
  </section>;
}
