"use client";

import { useCallback, useEffect, useState } from "react";
import { Award, Trash2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import ItemView from "@/components/intuitions/ItemView";
import { errorMessage } from "@/components/reward-models/rm-text";
import { imDeleteExample, imEditExample, imExamples, type Example } from "@/lib/intuition-api";
import { wzHealth, type Health, type SimilarPair } from "@/lib/wizard-api";
import { CardShell, NeedsModel, useWizard } from "../wizard-ui";

function PairRow({ pair, examples, labels, kind, onChanged }: { pair: SimilarPair; examples: Map<string, Example>; labels: string[]; kind: "duplicate" | "lookalike"; onChanged: () => void }) {
  const { modelId } = useWizard();
  const [error, setError] = useState("");
  const a = examples.get(pair.a), b = examples.get(pair.b);
  if (!modelId || !a || !b) return null;
  const act = (fn: () => Promise<unknown>) => fn().then(onChanged).catch((e) => setError(errorMessage(e)));
  return (
    <li className="rounded-md border border-border p-2.5">
      <div className="grid gap-2 sm:grid-cols-2">
        {[a, b].map((e) => (
          <div key={e.id} className="min-w-0 space-y-1.5">
            <div className="max-h-32 overflow-hidden"><ItemView item={e.item} /></div>
            <div className="flex flex-wrap items-center gap-1">
              {kind === "lookalike"
                ? labels.map((l) => <Button key={l} size="xs" variant={e.label === l ? "default" : "outline"} onClick={() => void act(() => imEditExample(modelId, e.id, { label: l }))}>{l}</Button>)
                : <span className="font-mono text-[11px] text-muted-foreground">{e.label}</span>}
              <Button size="xs" variant="ghost" aria-label="Remove example" title="Remove this example" onClick={() => void act(() => imDeleteExample(modelId, e.id))}><Trash2 /></Button>
            </div>
          </div>
        ))}
      </div>
      <p className="m-0 mt-1.5 text-[11px] text-muted-foreground">{Math.round(pair.similarity * 100)}% similar{kind === "lookalike" ? " · labeled differently: is one of them wrong, or is there a difference a criterion should capture?" : " · keep one"}</p>
      {error && <p role="alert" className="m-0 text-[11px] text-destructive">{error}</p>}
    </li>
  );
}

/** The curated examples the judge learns from and is measured on: coverage, pins, and hygiene. */
export default function GoldenCard() {
  const { modelId, send, refresh, version } = useWizard();
  const [health, setHealth] = useState<Health | null>(null);
  const [examples, setExamples] = useState<Example[]>([]);
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    if (!modelId) return;
    try {
      const [h, ex] = await Promise.all([wzHealth(modelId), imExamples(modelId)]);
      setHealth(h); setExamples(ex);
    } catch (e) { setError(errorMessage(e)); }
  }, [modelId]);
  useEffect(() => { void load(); }, [load, version]);

  if (!modelId) return <CardShell icon={Award} title="Health check"><NeedsModel /></CardShell>;
  const byId = new Map(examples.map((e) => [e.id, e]));
  const labels = health?.coverage.map((c) => c.label) ?? [];
  const max = Math.max(1, ...(health?.coverage.map((c) => c.total) ?? [1]));
  const changed = () => { void load(); refresh(); };


  return (
    <CardShell
      icon={Award}
      title="Golden set"
      subtitle={health ? `${health.labeled} labeled · ${health.pinned} pinned · ${health.calibration} in calibration` : "Loading…"}
      actions={health && health.needs_label > 0 ? <Button size="xs" variant="ghost" onClick={() => send("Open the labeler for the examples that still need labels.")}>{health.needs_label} need labels</Button> : undefined}
    >
      {error && <p role="alert" className="m-0 mb-2 text-[11.5px] text-destructive">{error}</p>}
      {health && (
        <div className="flex flex-col gap-4">
          <section>
            <h4 className="m-0 mb-1.5 text-[11px] font-semibold tracking-wide text-muted-foreground uppercase">Coverage</h4>
            <div className="space-y-1.5">
              {health.coverage.map((c) => (
                <div key={c.label} className="grid grid-cols-[7rem_1fr_9rem] items-center gap-2.5 text-[12px]">
                  <span className="truncate font-mono">{c.label}</span>
                  <div className="flex h-2 overflow-hidden rounded-full bg-raised" title={`${c.total - c.held_out} train, ${c.held_out} held out`}>
                    <div className="h-full bg-brand-500" style={{ width: `${((c.total - c.held_out) / max) * 100}%` }} />
                    <div className="h-full bg-brand-500/40" style={{ width: `${(c.held_out / max) * 100}%` }} />
                  </div>
                  <span className="text-right tabular-nums text-muted-foreground">{c.total} · {c.held_out} held out · {c.pinned} pinned</span>
                </div>
              ))}
            </div>
          </section>

          {health.issues.length > 0 && (
            <ul className="m-0 list-none space-y-1 p-0">
              {health.issues.map((i) => <li key={i} className="rounded-md border border-yellow-500/30 bg-yellow-500/8 px-2.5 py-1.5 text-[11.5px] text-yellow-900 dark:text-yellow-200">{i}</li>)}
            </ul>
          )}

          {health.lookalikes.length > 0 && (
            <section>
              <h4 className="m-0 mb-1.5 text-[11px] font-semibold tracking-wide text-muted-foreground uppercase">Look alike, labeled differently</h4>
              <ul className="m-0 list-none space-y-2 p-0">{health.lookalikes.slice(0, 5).map((p) => <PairRow key={p.a + p.b} pair={p} examples={byId} labels={labels} kind="lookalike" onChanged={changed} />)}</ul>
            </section>
          )}
          {health.duplicates.length > 0 && (
            <section>
              <h4 className="m-0 mb-1.5 text-[11px] font-semibold tracking-wide text-muted-foreground uppercase">Near-duplicates</h4>
              <ul className="m-0 list-none space-y-2 p-0">{health.duplicates.slice(0, 5).map((p) => <PairRow key={p.a + p.b} pair={p} examples={byId} labels={labels} kind="duplicate" onChanged={changed} />)}</ul>
            </section>
          )}
        </div>
      )}
    </CardShell>
  );
}
