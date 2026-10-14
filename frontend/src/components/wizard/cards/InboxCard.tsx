"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { Inbox, Pin } from "lucide-react";
import { Button } from "@/components/ui/button";
import ItemView from "@/components/intuitions/ItemView";
import { errorMessage } from "@/components/reward-models/rm-text";
import { imGet } from "@/lib/intuition-api";
import { wzQueue, wzResolve, wzTriage, type QueueRow } from "@/lib/wizard-api";
import { cn } from "@/lib/utils";
import { CardShell, NeedsModel, pct, useWizard } from "../wizard-ui";

type Queue = "triage" | "expert";
const said = (row: QueueRow) => String(row.output.label ?? row.output.winner ?? "");
const TRIAGE = [
  { key: "y", action: "looks_right", label: "Looks right" },
  { key: "n", action: "escalate", label: "Needs review" },
  { key: "x", action: "ignore", label: "Ignore" },
] as const;

function Subject({ row }: { row: QueueRow }) {
  return (
    <div className="max-h-72 overflow-y-auto rounded-md border border-border bg-surface/30 p-3">
      {row.kind === "compare" && row.input.item_b ? (
        <div className="grid gap-3 sm:grid-cols-2">
          <div><div className="mb-1 text-[10.5px] font-semibold text-muted-foreground">A</div><ItemView item={row.input.item} clamp={false} /></div>
          <div><div className="mb-1 text-[10.5px] font-semibold text-muted-foreground">B</div><ItemView item={row.input.item_b} clamp={false} /></div>
        </div>
      ) : <ItemView item={row.input.item} clamp={false} />}
    </div>
  );
}

/**
 * The review inbox. Triage is a fast keyboard pass over what the judge decided
 * (looks right / needs review / ignore); the expert queue fills in the right
 * answer and why, and can pin it as a case the judge must never get wrong.
 */
export default function InboxCard({ queue: initial = "triage", topic = null }: { queue?: Queue; topic?: string | null }) {
  const { modelId, send, refresh, version } = useWizard();
  const [queue, setQueue] = useState<Queue>(initial);
  const [rows, setRows] = useState<QueueRow[] | null>(null);
  const [labels, setLabels] = useState<string[]>([]);
  const [tally, setTally] = useState<Record<string, number>>({});
  const [note, setNote] = useState("");
  const [choice, setChoice] = useState<string | null>(null);
  const [pin, setPin] = useState(false);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    if (!modelId) return;
    try {
      const [detail, q] = await Promise.all([imGet(modelId), wzQueue(modelId, queue, topic)]);
      const v = detail.active ?? detail.draft;
      setLabels(detail.model.output_type === "choice" ? (v?.labels ?? []).map((l) => l.id) : ["good", "bad"]);
      setRows(q.items);
    } catch (e) { setError(errorMessage(e)); }
  }, [modelId, queue, topic]);
  useEffect(() => { void load(); }, [load, version]);

  const current = rows?.[0];
  const options = useMemo(() => (current?.kind === "compare" ? ["a", "b"] : labels), [current, labels]);
  useEffect(() => { setNote(""); setChoice(null); setPin(false); }, [current?.id]);

  const advance = useCallback((key: string) => {
    setRows((r) => (r ? r.slice(1) : r));
    setTally((t) => ({ ...t, [key]: (t[key] ?? 0) + 1 }));
  }, []);

  const triage = useCallback(async (action: (typeof TRIAGE)[number]["action"]) => {
    if (!modelId || !current || busy) return;
    setBusy(true); setError("");
    try { await wzTriage(modelId, current.id, action, note.trim()); advance(action); }
    catch (e) { setError(errorMessage(e)); } finally { setBusy(false); }
  }, [modelId, current, busy, note, advance]);

  async function resolve() {
    if (!modelId || !current || !choice) return;
    setBusy(true); setError("");
    try {
      await wzResolve(modelId, current.id, { label: choice, note: note.trim(), pin });
      advance(choice === said(current) ? "confirmed" : "corrected");
      if (pin) setTally((t) => ({ ...t, pinned: (t.pinned ?? 0) + 1 }));
    } catch (e) { setError(errorMessage(e)); } finally { setBusy(false); }
  }

  useEffect(() => {
    if (!current || queue !== "triage") return;
    const onKey = (e: KeyboardEvent) => {
      const target = e.target as HTMLElement | null;
      if (target && /input|textarea|select/i.test(target.tagName)) return;
      const hit = TRIAGE.find((t) => t.key === e.key.toLowerCase());
      if (hit) { e.preventDefault(); void triage(hit.action); }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [current, queue, triage]);

  if (!modelId) return <CardShell icon={Inbox} title="Inbox"><NeedsModel /></CardShell>;
  const reviewed = Object.entries(tally).filter(([k]) => k !== "pinned").reduce((n, [, v]) => n + v, 0);

  function done() {
    refresh();
    const parts = Object.entries(tally).map(([k, v]) => `${v} ${k.replace("_", " ")}`);
    send(reviewed ? `Reviewed ${reviewed} in the ${queue} queue: ${parts.join(", ")}.` : `Closed the ${queue} queue.`, "event");
    setTally({});
  }

  return (
    <CardShell
      icon={Inbox}
      title="Inbox"
      subtitle={rows ? `${rows.length} ${queue === "triage" ? "to triage · least confident first" : "escalated"}${topic ? " · one topic" : ""}` : "Loading…"}
      actions={reviewed > 0 ? <Button size="xs" variant="ghost" onClick={done}>Done</Button> : undefined}
    >
      <div role="tablist" aria-label="Queue" className="mb-3 inline-flex rounded-md border border-border p-0.5 text-[12px]">
        {(["triage", "expert"] as const).map((q) => (
          <button key={q} role="tab" type="button" aria-selected={queue === q} onClick={() => { setQueue(q); setRows(null); }} className={cn("rounded px-2.5 py-1", queue === q ? "bg-foreground text-background" : "text-muted-foreground hover:text-foreground")}>
            {q === "triage" ? "Triage" : "Expert review"}
          </button>
        ))}
      </div>
      {error && <p role="alert" className="m-0 mb-2 text-[11.5px] text-destructive">{error}</p>}
      {rows && !current && (
        <p className="m-0 text-[12px] text-muted-foreground">
          {reviewed ? "All caught up." : queue === "triage" ? "Nothing to triage. Decisions from the playground and the API land here." : "Nothing escalated. Mark items \"Needs review\" in triage to send them here."}
        </p>
      )}
      {current && (
        <div className="space-y-2.5">
          <Subject row={current} />
          <p className="m-0 text-[12px] text-muted-foreground">
            The judge said <b className="text-foreground">{said(current)}</b> ({pct(current.confidence)} sure) · v{current.version} · {current.caller}
            {current.escalation_note && <> · flagged: <i>{current.escalation_note}</i></>}
          </p>
          {queue === "triage" ? (
            <>
              <input aria-label="Note (optional)" value={note} onChange={(e) => setNote(e.target.value)} placeholder="Why? (optional, kept with the item)" className="w-full rounded-md border border-border bg-background px-2.5 py-1.5 text-[12px] outline-none focus:border-foreground/40" />
              <div className="flex flex-wrap gap-1.5">
                {TRIAGE.map((t) => (
                  <Button key={t.action} size="sm" variant={t.action === "looks_right" ? "default" : t.action === "escalate" ? "outline" : "ghost"} disabled={busy} onClick={() => void triage(t.action)}>
                    <kbd className="mr-1 rounded border border-current/30 px-1 font-mono text-[10px] opacity-70">{t.key.toUpperCase()}</kbd>{t.label}
                  </Button>
                ))}
              </div>
            </>
          ) : (
            <>
              <div className="flex flex-wrap items-center gap-1.5 text-[12px]">
                <span className="text-muted-foreground">Right answer:</span>
                {options.map((l) => <Button key={l} size="xs" variant={choice === l ? "default" : "outline"} onClick={() => setChoice(l)}>{l}{l === said(current) ? " (judge)" : ""}</Button>)}
              </div>
              <textarea aria-label="Why" rows={2} value={note} onChange={(e) => setNote(e.target.value)} placeholder="Why is that the right answer? Reasons become criteria." className="w-full resize-y rounded-md border border-border bg-background px-2.5 py-1.5 text-[12px] outline-none focus:border-foreground/40" />
              <div className="flex flex-wrap items-center gap-3">
                <label className="flex items-center gap-1.5 text-[12px]"><input type="checkbox" checked={pin} onChange={(e) => setPin(e.target.checked)} /><Pin className="size-3" />Must never get this wrong (pin)</label>
                <span className="flex-1" />
                <Button size="sm" disabled={!choice || busy} onClick={() => void resolve()}>Add to golden set</Button>
              </div>
            </>
          )}
        </div>
      )}
    </CardShell>
  );
}
