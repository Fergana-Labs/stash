"use client";

import { ShieldCheck } from "lucide-react";
import type { HardenResult } from "@/lib/wizard-api";
import { CardShell, pct, Stat } from "../wizard-ui";

/** Before/after attack success on held-out items, and the attacks that got through. */
export default function RobustnessCard({ result }: { result?: HardenResult }) {
  if (!result) return <CardShell icon={ShieldCheck} title="Robustness"><p className="m-0 text-[12px] text-muted-foreground">Ask the wizard to harden the model.</p></CardShell>;
  const before = result.before.success_rate, after = result.after.success_rate;
  const accBefore = result.holdout_accuracy.before, accAfter = result.holdout_accuracy.after;
  return (
    <CardShell icon={ShieldCheck} title="Robustness" subtitle={`Attacks trying to force “${result.target}”`}>
      <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
        <Stat label="Attack success before" value={pct(before)} hint={`${result.before.fooled} of ${result.before.attempts} attempts`} tone={before ? "bad" : undefined} />
        <Stat label="After repair" value={pct(after)} hint={`${result.after.fooled} of ${result.after.attempts} attempts`} tone={after != null && before != null && after < before ? "good" : undefined} />
        <Stat label="Repairs learned" value={String(result.repairs_added)} hint={`from ${result.found_in_training.fooled} training attacks`} />
        <Stat label="Held-out accuracy" value={pct(accAfter)} hint={accBefore != null ? `was ${pct(accBefore)}` : undefined} tone={accAfter != null && accBefore != null && accAfter < accBefore ? "bad" : undefined} />
      </div>
      {result.before.examples.length > 0 && (
        <div className="mt-3">
          <div className="mb-1 text-[10.5px] font-medium tracking-wide text-muted-foreground uppercase">Attacks that worked before repair</div>
          <ul className="m-0 list-none space-y-1 p-0">
            {result.before.examples.slice(0, 3).map((e, i) => (
              <li key={i} className="rounded border border-border bg-surface/40 px-2 py-1 font-mono text-[11px] break-words whitespace-pre-wrap">{e.attack}</li>
            ))}
          </ul>
        </div>
      )}
      <p className="m-0 mt-3 text-[11px] text-muted-foreground">{result.note} {result.gate.passed ? "The regression gate passes." : "The regression gate is blocking this version — see the training report."}</p>
    </CardShell>
  );
}
