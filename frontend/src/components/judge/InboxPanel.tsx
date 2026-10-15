"use client";

import { useCallback, useEffect, useState } from "react";
import { Layers, Pin } from "lucide-react";
import { Button } from "@/components/ui/button";
import { errorMessage } from "@/components/reward-models/rm-text";
import { imGet } from "@/lib/intuition-api";
import { wzQueue, wzRefreshTopics, wzResolve, wzTopics, wzTriage, type QueueRow, type Topic } from "@/lib/wizard-api";
import { LabelChip, LabelPicker, labelSpace, PAIR_SPACE, type LabelSpace } from "@/components/wizard/labels";
import { pct, useWizard } from "@/components/wizard/wizard-ui";
import { Badge, FilterChips, ItemRow } from "./ItemRow";

const said = (row: QueueRow) => String(row.output.label ?? row.output.winner ?? "");

function Review({ row, space, onDone }: { row: QueueRow; space: LabelSpace; onDone: (outcome: string) => void }) {
  const { modelId } = useWizard();
  const [value, setValue] = useState<string | null>(said(row));
  const [note, setNote] = useState("");
  const [pin, setPin] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  async function save(label: string) {
    if (!modelId) return;
    setBusy(true); setError("");
    try { await wzResolve(modelId, row.id, { label, note: note.trim(), pin }); onDone(label === said(row) ? "confirmed" : "corrected"); }
    catch (e) { setError(errorMessage(e)); setBusy(false); }
  }
  async function ignore() {
    if (!modelId) return;
    setBusy(true);
    try { await wzTriage(modelId, row.id, "ignore"); onDone("ignored"); } catch (e) { setError(errorMessage(e)); setBusy(false); }
  }
  async function escalate() {
    if (!modelId) return;
    setBusy(true); setError("");
    try { await wzTriage(modelId, row.id, "escalate", note.trim()); onDone("flagged for expert review"); }
    catch (e) { setError(errorMessage(e)); setBusy(false); }
  }
  return (
    <div className="space-y-2.5">
      <p className="m-0 text-[12px] text-muted-foreground">Right answer? The intuition&apos;s pick is preselected{space.kind === "multi" ? " — toggle issues, then save" : " — click it to confirm, or pick another"}.</p>
      <LabelPicker space={row.kind === "compare" ? PAIR_SPACE : space} value={value} suggested={said(row)} disabled={busy} commitLabel="Save" onPick={(label, go) => { setValue(label); if (go) void save(label); }} />
      <div className="flex flex-wrap items-center gap-2">
        <input aria-label="Why" value={note} onChange={(e) => setNote(e.target.value)} placeholder="Why? (reasons become new criteria)" className="min-w-0 flex-1 rounded-md border border-border bg-background px-2.5 py-1.5 text-[12px] outline-none focus:border-foreground/40" />
        <label className="flex items-center gap-1 text-[11.5px] text-muted-foreground"><input type="checkbox" checked={pin} onChange={(e) => setPin(e.target.checked)} /><Pin className="size-3" />Must get right</label>
        {row.status !== "escalated" && <Button size="sm" variant="outline" disabled={busy} onClick={() => void escalate()}>Needs expert review</Button>}
        <Button size="sm" variant="ghost" disabled={busy} onClick={() => void ignore()} title="Not useful as an example (spam, duplicate, out of scope)">Ignore</Button>
      </div>
      {error && <p role="alert" className="m-0 text-[11.5px] text-destructive">{error}</p>}
    </div>
  );
}

/**
 * The inbox: raw decisions from real traffic (API, MCP, Try it), least confident
 * first. Confirming or correcting one moves it into the golden set.
 */
export default function InboxPanel({ compact = false }: { compact?: boolean }) {
  const { modelId, send, refresh, version } = useWizard();
  const [rows, setRows] = useState<QueueRow[] | null>(null);
  const [space, setSpace] = useState<LabelSpace | null>(null);
  const [topics, setTopics] = useState<Topic[]>([]);
  const [topic, setTopic] = useState("all");
  const [open, setOpen] = useState<string | null>(null);
  const [tally, setTally] = useState<Record<string, number>>({});
  const [grouping, setGrouping] = useState(false);
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    if (!modelId) return;
    try {
      const [detail, q, t] = await Promise.all([imGet(modelId), wzQueue(modelId, "all", topic === "all" ? null : topic), wzTopics(modelId)]);
      setSpace(labelSpace(detail)); setRows(q.items); setTopics(t.topics);
    } catch (e) { setError(errorMessage(e)); }
  }, [modelId, topic]);
  useEffect(() => { void load(); }, [load, version]);

  async function group() {
    if (!modelId) return;
    setGrouping(true); setError("");
    try { setTopics((await wzRefreshTopics(modelId)).topics); } catch (e) { setError(errorMessage(e)); } finally { setGrouping(false); }
  }

  function done(id: string, outcome: string) {
    setRows((r) => r?.filter((x) => x.id !== id) ?? r);
    setOpen((o) => (o === id ? null : o));
    setTally((t) => ({ ...t, [outcome]: (t[outcome] ?? 0) + 1 }));
  }
  const reviewed = Object.values(tally).reduce((a, b) => a + b, 0);
  function report() {
    refresh();
    send(`Reviewed ${reviewed} from the inbox: ${Object.entries(tally).map(([k, v]) => `${v} ${k}`).join(", ")}.`, "event");
    setTally({});
  }

  const shown = compact ? (rows ?? []).slice(0, 5) : rows ?? [];
  return (
    <div className="flex flex-col gap-3">
      {!compact && (
        <div className="flex flex-wrap items-start justify-between gap-3">
          <p className="m-0 max-w-xl text-[12.5px] text-muted-foreground">What your intuition decided on real inputs (API, MCP, Try it), least confident first. Confirm or correct each; it joins your golden set and teaches the next version.</p>
          {reviewed > 0 && <Button size="sm" variant="outline" onClick={report}>Done ({reviewed} reviewed)</Button>}
        </div>
      )}
      {!compact && (
        <div className="flex flex-wrap items-center gap-2">
          {topics.length > 0 && (
            <FilterChips value={topic} onChange={(t) => { setTopic(t); setRows(null); }} options={[{ id: "all", label: "All" }, ...topics.map((t) => ({ id: t.id, label: t.name, count: t.unreviewed, title: `${t.description}${t.reviewed ? ` · overruled ${t.overturned} of ${t.reviewed} reviewed` : ""}` }))]} />
          )}
          <Button size="xs" variant="ghost" disabled={grouping} onClick={() => void group()} title="Group similar inputs into topics, so you can review one kind at a time and see where it gets overruled">
            <Layers />{grouping ? "Grouping…" : topics.length ? "Regroup by topic" : "Group by topic"}
          </Button>
        </div>
      )}
      {error && <p role="alert" className="m-0 text-[11.5px] text-destructive">{error}</p>}
      {rows === null && <p role="status" className="m-0 text-[12px] text-muted-foreground">Loading…</p>}
      {rows && rows.length === 0 && <p className="m-0 rounded-lg border border-dashed border-border p-6 text-center text-[12.5px] text-muted-foreground">{reviewed ? "All caught up." : "Nothing to review yet. Decisions from the API, MCP and Try it land here."}</p>}
      <ul className="m-0 list-none space-y-2 p-0">
        {shown.map((row) => (
          <ItemRow
            key={row.id}
            item={row.input.item}
            itemB={row.kind === "compare" ? row.input.item_b : null}
            open={open === row.id}
            onToggle={() => setOpen(open === row.id ? null : row.id)}
            badges={<><Badge>{row.caller}</Badge><span>v{row.version}</span><span>{new Date(row.created_at).toLocaleString()}</span>{row.status === "escalated" && <Badge tone="warn">flagged{row.escalation_note ? `: ${row.escalation_note}` : ""}</Badge>}</>}
            decision={<><LabelChip label={said(row)} kind={space?.kind} tone="judge" /><span className="text-[11px] tabular-nums text-muted-foreground">{pct(row.confidence)} sure</span></>}
          >
            {space && <Review row={row} space={space} onDone={(o) => done(row.id, o)} />}
          </ItemRow>
        ))}
      </ul>
      {compact && rows && rows.length > 5 && <p className="m-0 text-[11.5px] text-muted-foreground">{rows.length - 5} more in the Inbox tab.</p>}
      {compact && reviewed > 0 && <Button size="xs" variant="ghost" onClick={report}>Done</Button>}
    </div>
  );
}
