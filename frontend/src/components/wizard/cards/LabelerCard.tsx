"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { ChevronLeft, Tags } from "lucide-react";
import { Button } from "@/components/ui/button";
import ItemView from "@/components/intuitions/ItemView";
import { errorMessage } from "@/components/reward-models/rm-text";
import { imEditExample, imExamples, imGet, type Example, type OutputLabel } from "@/lib/intuition-api";
import { wzReport } from "@/lib/wizard-api";
import { CardShell, NeedsModel, useWizard } from "../wizard-ui";

type Which = "needs_review" | "all" | "mistakes";

/** One item at a time, a button (and number key) per label. Pairs get A / B. */
export default function LabelerCard({ which = "needs_review" }: { which?: Which }) {
  const { modelId, send, refresh } = useWizard();
  const [queue, setQueue] = useState<Example[] | null>(null);
  const [labels, setLabels] = useState<OutputLabel[]>([]);
  const [index, setIndex] = useState(0);
  const [done, setDone] = useState<Record<string, string>>({});
  const [error, setError] = useState("");
  const [finished, setFinished] = useState(false);

  useEffect(() => {
    if (!modelId) return;
    (async () => {
      try {
        const [detail, examples] = await Promise.all([imGet(modelId), imExamples(modelId)]);
        const v = detail.draft ?? detail.active;
        setLabels(detail.model.output_type === "choice" ? v?.labels ?? [] : [{ id: "good", description: "A good output" }, { id: "bad", description: "A poor output" }]);
        let picked = examples;
        if (which === "needs_review") picked = examples.filter((e) => e.needs_review);
        if (which === "mistakes") {
          const report = (await wzReport(modelId)).report;
          const wrong = new Set((report?.holdout.rows ?? []).filter((r) => r.predicted !== r.label).map((r) => r.example_id));
          picked = examples.filter((e) => wrong.has(e.id));
        }
        setQueue(picked);
      } catch (e) { setError(errorMessage(e)); }
    })();
  }, [modelId, which]);

  const current = queue?.[index];
  const options = useMemo(() => (current?.kind === "pair" ? [{ id: "a", description: "A is better" }, { id: "b", description: "B is better" }] : labels), [current, labels]);

  const finish = useCallback((labeled: Record<string, string>) => {
    if (finished) return;
    setFinished(true);
    refresh();
    const counts = Object.values(labeled).reduce<Record<string, number>>((acc, l) => ({ ...acc, [l]: (acc[l] ?? 0) + 1 }), {});
    const summary = Object.entries(counts).map(([l, n]) => `${n} ${l}`).join(", ");
    send(Object.keys(labeled).length ? `Labeled ${Object.keys(labeled).length} example${Object.keys(labeled).length === 1 ? "" : "s"}: ${summary}.` : "Closed the labeler without labeling.", "event");
  }, [finished, refresh, send]);

  const label = useCallback(async (value: string) => {
    if (!modelId || !current || !queue) return;
    setError("");
    try {
      await imEditExample(modelId, current.id, { label: value, needs_review: false });
      const next = { ...done, [current.id]: value };
      setDone(next);
      if (index + 1 >= queue.length) finish(next); else setIndex(index + 1);
    } catch (e) { setError(errorMessage(e)); }
  }, [modelId, current, queue, done, index, finish]);

  useEffect(() => {
    if (finished || !current) return;
    const onKey = (e: KeyboardEvent) => {
      const target = e.target as HTMLElement | null;
      if (target && /input|textarea|select/i.test(target.tagName)) return;
      const n = Number(e.key);
      if (n >= 1 && n <= options.length) { e.preventDefault(); void label(options[n - 1].id); }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [finished, current, options, label]);

  if (!modelId) return <CardShell icon={Tags} title="Label examples"><NeedsModel /></CardShell>;
  const total = queue?.length ?? 0;
  const labeledCount = Object.keys(done).length;

  return (
    <CardShell
      icon={Tags}
      title="Label examples"
      subtitle={queue ? (finished ? `Done — ${labeledCount} labeled` : `${Math.min(index + 1, total)} of ${total} · press 1–${options.length}`) : "Loading…"}
      actions={!finished && queue && total > 0 ? <Button size="xs" variant="ghost" onClick={() => finish(done)}>Done</Button> : undefined}
    >
      {error && <p role="alert" className="m-0 mb-2 text-[11.5px] text-destructive">{error}</p>}
      {queue && total === 0 && <p className="m-0 text-[12px] text-muted-foreground">{which === "mistakes" ? "No held-out mistakes to review." : "Nothing needs a label right now."}</p>}
      {queue && total > 0 && !finished && current && (
        <>
          <div className="mb-3 h-1 overflow-hidden rounded-full bg-raised"><div className="h-full rounded-full bg-brand-500 transition-all" style={{ width: `${(labeledCount / total) * 100}%` }} /></div>
          <div className="max-h-80 overflow-y-auto rounded-md border border-border bg-surface/30 p-3">
            {current.kind === "pair" && current.item_b ? (
              <div className="grid gap-3 sm:grid-cols-2">
                <div><div className="mb-1 text-[10.5px] font-semibold text-muted-foreground">A</div><ItemView item={current.item} clamp={false} /></div>
                <div><div className="mb-1 text-[10.5px] font-semibold text-muted-foreground">B</div><ItemView item={current.item_b} clamp={false} /></div>
              </div>
            ) : <ItemView item={current.item} clamp={false} />}
          </div>
          {current.note && <p className="m-0 mt-1.5 text-[11px] text-muted-foreground">{current.note}</p>}
          <div className="mt-3 flex flex-wrap gap-1.5">
            {options.map((o, i) => (
              <Button key={o.id} size="sm" variant={current.label === o.id ? "secondary" : "outline"} title={o.description} onClick={() => void label(o.id)}>
                <kbd className="mr-1 rounded border border-border px-1 font-mono text-[10px] text-muted-foreground">{i + 1}</kbd>{o.id}
              </Button>
            ))}
            <span className="flex-1" />
            <Button size="sm" variant="ghost" disabled={index === 0} aria-label="Previous" onClick={() => setIndex(index - 1)}><ChevronLeft /></Button>
            <Button size="sm" variant="ghost" onClick={() => (index + 1 >= total ? finish(done) : setIndex(index + 1))}>Skip</Button>
          </div>
        </>
      )}
      {finished && <p className="m-0 text-[12px] text-muted-foreground">Thanks — the wizard has your labels.</p>}
    </CardShell>
  );
}
