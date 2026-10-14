"use client";

import { use, useCallback, useEffect, useState } from "react";
import { Check } from "lucide-react";
import { Button } from "@/components/ui/button";
import ItemView from "@/components/intuitions/ItemView";
import { reviewRate, reviewView, type ReviewView } from "@/lib/wizard-api";
import { cn } from "@/lib/utils";

/**
 * Calibration review for an invited reviewer: no account, no other reviewers'
 * labels. The link's token is the only credential.
 */
export default function ReviewPage({ params }: { params: Promise<{ token: string }> }) {
  const { token } = use(params);
  const [view, setView] = useState<ReviewView | null>(null);
  const [index, setIndex] = useState(0);
  const [note, setNote] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    reviewView(token).then((v) => {
      setView(v);
      const firstOpen = v.items.findIndex((i) => !i.my_label);
      setIndex(firstOpen < 0 ? v.items.length : firstOpen);
    }).catch((e) => setError(e instanceof Error ? e.message : String(e)));
  }, [token]);

  const current = view?.items[index];
  useEffect(() => setNote(current?.my_note ?? ""), [current?.id, current?.my_note]);

  const rate = useCallback(async (label: string) => {
    if (!view || !current || busy) return;
    setBusy(true); setError("");
    try {
      await reviewRate(token, current.id, label, note.trim());
      setView({ ...view, items: view.items.map((i) => (i.id === current.id ? { ...i, my_label: label, my_note: note.trim() } : i)) });
      setIndex(index + 1);
    } catch (e) { setError(e instanceof Error ? e.message : String(e)); } finally { setBusy(false); }
  }, [view, current, busy, token, note, index]);

  useEffect(() => {
    if (!current || !view) return;
    const onKey = (e: KeyboardEvent) => {
      if ((e.target as HTMLElement | null)?.tagName?.match(/input|textarea/i)) return;
      const n = Number(e.key);
      if (n >= 1 && n <= view.labels.length) { e.preventDefault(); void rate(view.labels[n - 1].id); }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [current, view, rate]);

  if (!view) return <main className="grid min-h-dvh place-items-center bg-background p-4 text-sm text-muted-foreground">{error || "Loading…"}</main>;
  const done = view.items.filter((i) => i.my_label).length;
  const total = view.items.length;

  return (
    <main className="min-h-dvh bg-background text-foreground">
      <div className="mx-auto max-w-2xl px-4 py-8">
        <p className="m-0 text-[12px] text-muted-foreground">Review for {view.reviewer}</p>
        <h1 className="m-0 mt-0.5 text-xl font-semibold tracking-tight">{view.model}</h1>
        <p className="mt-2 text-[13px] whitespace-pre-wrap text-muted-foreground">{view.instructions}</p>
        <ul className="m-0 mt-3 list-none space-y-1 p-0 text-[12.5px]">
          {view.labels.map((l, i) => {
            const boundary = view.label_boundaries?.find((b) => b.id === l.id);
            return <li key={l.id}><kbd className="mr-1.5 rounded border border-border px-1 font-mono text-[10.5px]">{i + 1}</kbd><b className="font-mono">{l.id}</b> — {boundary?.means || l.description}{boundary?.not && <span className="text-muted-foreground"> (not: {boundary.not})</span>}</li>;
          })}
        </ul>
        <p className="mt-3 text-[12px] text-muted-foreground">Label each one the way you would on the job. You won’t see anyone else’s answers, and they won’t see yours until everyone is compared.</p>

        <div className="mt-5 h-1 overflow-hidden rounded-full bg-raised"><div className="h-full rounded-full bg-brand-500 transition-all" style={{ width: `${total ? (done / total) * 100 : 0}%` }} /></div>
        <p className="m-0 mt-1 text-[11.5px] text-muted-foreground tabular-nums">{done} of {total} done</p>
        {error && <p role="alert" className="text-[12px] text-destructive">{error}</p>}

        {current ? (
          <section aria-label={`Item ${index + 1}`} className="mt-4 space-y-3">
            <div className="max-h-[50vh] overflow-y-auto rounded-lg border border-border bg-surface/30 p-4">
              {current.item_b ? (
                <div className="grid gap-3 sm:grid-cols-2"><div><div className="mb-1 text-[10.5px] font-semibold text-muted-foreground">A</div><ItemView item={current.item} clamp={false} /></div><div><div className="mb-1 text-[10.5px] font-semibold text-muted-foreground">B</div><ItemView item={current.item_b} clamp={false} /></div></div>
              ) : <ItemView item={current.item} clamp={false} />}
            </div>
            <input aria-label="Why (optional)" value={note} onChange={(e) => setNote(e.target.value)} placeholder="Why? (optional — especially when it's a close call)" className="w-full rounded-md border border-border bg-background px-3 py-2 text-[13px] outline-none focus:border-foreground/40" />
            <div className="flex flex-wrap gap-2">
              {view.labels.map((l, i) => (
                <Button key={l.id} variant={current.my_label === l.id ? "default" : "outline"} disabled={busy} onClick={() => void rate(l.id)}>
                  <kbd className="mr-1 rounded border border-current/30 px-1 font-mono text-[10px] opacity-70">{i + 1}</kbd>{l.id}
                </Button>
              ))}
            </div>
          </section>
        ) : (
          <div className="mt-6 rounded-lg border border-border p-6 text-center">
            <Check className="mx-auto size-6 text-emerald-600" />
            <p className="m-0 mt-2 text-[14px] font-medium">All done — thank you.</p>
            <p className="m-0 mt-1 text-[12.5px] text-muted-foreground">You can change any answer below until the link is closed.</p>
          </div>
        )}

        <ol className="m-0 mt-6 flex list-none flex-wrap gap-1.5 p-0">
          {view.items.map((item, i) => (
            <li key={item.id}>
              <button type="button" aria-label={`Item ${i + 1}${item.my_label ? `: ${item.my_label}` : ""}`} onClick={() => setIndex(i)} className={cn("size-7 rounded-md border text-[11px] tabular-nums", i === index ? "border-foreground" : "border-border", item.my_label ? "bg-brand-500/15" : "bg-background")}>{i + 1}</button>
            </li>
          ))}
        </ol>
      </div>
    </main>
  );
}
