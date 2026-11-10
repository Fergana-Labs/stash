"use client";

import Link from "next/link";
import { useState } from "react";
import { Check, Loader2, X } from "lucide-react";
import { cn } from "@/lib/utils";
import { errorMessage, relativeTime } from "@/components/reward-models/rm-text";
import FileThumb from "./FileThumb";
import {
  evalExampleFilePath,
  type EvalChange, type EvalChangeCall, type EvalChangeExample, type EvalChanges as Changes, type EvalFlip, type EvalProposal, type EvalTally, type EvalTrait,
} from "@/lib/evals-api";

type Decision = "approve" | "reject";

const VERB: Record<string, string> = { add: "Add", tighten: "Tighten", fix: "Fix", point: "Point", remove: "Remove", request: "Change", write: "Rewrite", description: "Description", scoring: "Score by" };
const STATUS: Record<EvalProposal["status"], string> = { open: "Open", approved: "Approved", rejected: "Rejected" };
const SCORING = { mean: "Average", lowest: "Lowest trait" };
const sectionTitle = "m-0 text-[11px] font-medium uppercase tracking-wide text-muted-foreground";
const buttonClass = "h-6 rounded border border-border px-2 text-[12px] hover:bg-surface disabled:opacity-50";

/** What a proposal does, in a line: "Add Stripes, tighten Color". */
export function changeTitle(changes: EvalChange[]): string {
  const parts = changes.map((c, i) => {
    const verb = VERB[c.kind] ?? c.kind;
    return `${i === 0 ? verb : verb.toLowerCase()}${c.trait ? ` ${c.trait}` : ""}`;
  });
  return parts.slice(0, 3).join(", ") + (parts.length > 3 ? `, ${parts.length - 3} more` : "") || "Rubric change";
}

/** An eval's proposed rubric changes, like pull requests on the rubric: each shows what it
 * would change, what its checks measured, the examples and agent calls behind it, and is
 * approved or rejected here. The newest open one starts unfolded. */
export default function EvalChanges({ evalId, changes, onDecide }: {
  evalId: string;
  changes: Changes;
  onDecide: (proposalId: string, decision: Decision, note: string) => Promise<void>;
}) {
  const firstOpen = changes.proposals.find((p) => p.status === "open")?.id;
  const [toggled, setToggled] = useState<Record<string, boolean>>({});
  if (changes.proposals.length === 0) return <p className="text-[12px] text-muted-foreground">No proposed changes</p>;
  return <div className="space-y-2">
    {changes.proposals.map((p) => {
      const open = toggled[p.id] ?? p.id === firstOpen;
      return <Proposal key={p.id} evalId={evalId} proposal={p} open={open}
        onToggle={() => setToggled({ ...toggled, [p.id]: !open })} onDecide={(decision, note) => onDecide(p.id, decision, note)} />;
    })}
  </div>;
}

function Proposal({ evalId, proposal: p, open, onToggle, onDecide }: {
  evalId: string;
  proposal: EvalProposal;
  open: boolean;
  onToggle: () => void;
  onDecide: (decision: Decision, note: string) => Promise<void>;
}) {
  const status = p.stale ? "Out of date" : STATUS[p.status];
  return <article aria-label={`Change ${p.number}`} className="rounded border border-border text-[13px]">
    <button type="button" aria-expanded={open} onClick={onToggle} className="flex w-full items-baseline gap-2 px-3 py-2 text-left hover:bg-surface/40">
      <span className="tabular-nums text-muted-foreground">#{p.number}</span>
      <span className="min-w-0 flex-1 truncate font-medium">{changeTitle(p.changes)}</span>
      <span className={cn("whitespace-nowrap text-[12px]",
        p.stale || p.status === "rejected" ? "text-muted-foreground" : p.status === "approved" ? "text-emerald-700 dark:text-emerald-400" : "text-brand-600")}>{status}</span>
      <span className="whitespace-nowrap text-[12px] text-muted-foreground">{p.proposed_by ?? "Agent"}</span>
      <time className="whitespace-nowrap text-[12px] text-muted-foreground" dateTime={p.created_at}>{relativeTime(p.created_at)}</time>
    </button>
    {open && <div className="space-y-3 border-t border-border px-3 py-3">
      <div className="grid gap-4 md:grid-cols-[minmax(0,1fr)_260px]">
        <RubricDiff proposal={p} />
        <Checks proposal={p} />
      </div>
      <Examples evalId={evalId} proposal={p} />
      <CallList proposal={p} />
      {p.status === "open"
        ? <Decide proposal={p} onDecide={onDecide} />
        : <p className="m-0 text-[12px]">
          <span className="font-medium">{STATUS[p.status]}</span>
          {p.decided_by && <span> by {p.decided_by}</span>}
          {p.decided_at && <time className="ml-1.5 text-muted-foreground" dateTime={p.decided_at}>{relativeTime(p.decided_at)}</time>}
          {p.version && <span className="ml-1.5 text-muted-foreground">Rubric v{p.version}</span>}
          {p.note && <span className="ml-1.5 text-muted-foreground">“{p.note}”</span>}
        </p>}
    </div>}
  </article>;
}

// ── The rubric, before and after ─────────────────────────────────────────

const key = (name: string) => name.trim().toLowerCase();

function RubricDiff({ proposal: p }: { proposal: EvalProposal }) {
  const before = p.before?.traits ?? [];
  const old = new Map(before.map((t) => [key(t.name), t]));
  const now = new Map(p.traits.map((t) => [key(t.name), t]));
  const why = new Map(p.changes.filter((c) => c.trait).map((c) => [key(c.trait), c.why]));
  const changed = (a: EvalTrait, b: EvalTrait) => a.good !== b.good || a.bad !== b.bad;
  const added = p.traits.filter((t) => !old.has(key(t.name)));
  const edited = p.traits.filter((t) => old.has(key(t.name)) && changed(old.get(key(t.name))!, t));
  const removed = before.filter((t) => !now.has(key(t.name)));
  const unchanged = p.traits.length - added.length - edited.length;
  const general = p.changes.filter((c) => !c.trait && c.why && c.kind !== "description");
  return <section aria-label="Rubric changes" className="min-w-0 space-y-1.5">
    <h3 className={sectionTitle}>Rubric v{p.base}</h3>
    {general.map((c, i) => <p key={i} className="m-0 text-[12px] text-muted-foreground">{c.why}</p>)}
    {added.map((t) => <TraitDiff key={t.name} sign="+" name={t.name} why={why.get(key(t.name))} lines={[["+", "Good", t.good], ["+", "Bad", t.bad]]} />)}
    {edited.map((t) => {
      const was = old.get(key(t.name))!;
      const lines: Line[] = [];
      if (was.good !== t.good) lines.push(["-", "Good", was.good], ["+", "Good", t.good]);
      if (was.bad !== t.bad) lines.push(["-", "Bad", was.bad], ["+", "Bad", t.bad]);
      return <TraitDiff key={t.name} sign="~" name={t.name} why={why.get(key(t.name))} lines={lines} />;
    })}
    {removed.map((t) => <TraitDiff key={t.name} sign="-" name={t.name} why={why.get(key(t.name))} lines={[["-", "Good", t.good], ["-", "Bad", t.bad]]} />)}
    {p.before && p.before.scoring !== p.scoring && <TraitDiff sign="~" name="Scored by" lines={[["-", "", SCORING[p.before.scoring]], ["+", "", SCORING[p.scoring]]]} />}
    {p.before && p.before.instructions !== p.instructions && <TraitDiff sign="~" name="Description" lines={[["-", "", p.before.instructions], ["+", "", p.instructions]]} />}
    {unchanged > 0 && <p className="m-0 text-[12px] text-muted-foreground">{unchanged} {unchanged === 1 ? "trait" : "traits"} unchanged</p>}
  </section>;
}

type Line = ["+" | "-", string, string];

function TraitDiff({ sign, name, why, lines }: { sign: "+" | "-" | "~"; name: string; why?: string; lines: Line[] }) {
  return <div className="overflow-hidden rounded-sm border border-border">
    <div className="flex items-baseline gap-2 px-2 py-1">
      <span aria-hidden className={cn("w-3 font-mono text-[12px]", sign === "+" ? "text-emerald-700 dark:text-emerald-400" : sign === "-" ? "text-red-700 dark:text-red-400" : "text-muted-foreground")}>{sign}</span>
      <span className="font-medium">{name}</span>
      {why && <span title={why} className="line-clamp-2 min-w-0 flex-1 text-[12px] text-muted-foreground">{why}</span>}
    </div>
    {lines.filter(([, , text]) => text).map(([kind, label, text], i) => (
      <div key={i} className={cn("flex gap-2 border-l-2 px-2 py-0.5 text-[12px]", kind === "+" ? "border-l-emerald-600" : "border-l-red-500")}>
        <span aria-hidden className={cn("w-3 font-mono", kind === "+" ? "text-emerald-700 dark:text-emerald-400" : "text-red-700 dark:text-red-400")}>{kind}</span>
        {label && <span className="w-8 shrink-0 text-muted-foreground">{label}</span>}
        <span className={cn("min-w-0 flex-1", kind === "-" && "text-muted-foreground")}>{text}</span>
      </div>
    ))}
  </div>;
}

// ── Checks ───────────────────────────────────────────────────────────────

const ratio = (t: EvalTally) => `${t.right}/${t.n}`;

function Checks({ proposal: p }: { proposal: EvalProposal }) {
  const c = p.checks;
  if (!c) return <section aria-label="Checks"><h3 className={sectionTitle}>Checks</h3>
    <p role="status" className="m-0 mt-1.5 flex items-center gap-1 text-[12px] text-muted-foreground"><Loader2 className="size-3 animate-spin" />Checking</p></section>;
  const rows: { label: string; value: string; ok?: boolean; title?: string }[] = [];
  const { before: qb, after: qa } = p.quality;
  if (qa) rows.push({ label: "Quality", value: qb ? `${qb.score} → ${qa.score}` : `${qa.score}`, ok: qb ? qa.score >= qb.score : undefined });
  if (c.before && c.after) {
    if (c.after.fit.n > 0) rows.push({ label: "Learned from", value: `${ratio(c.before.fit)} → ${ratio(c.after.fit)}`, ok: c.after.fit.right >= c.before.fit.right });
    if (c.after.check.n > 0) rows.push({ label: "Held out", value: `${ratio(c.before.check)} → ${ratio(c.after.check)}`, ok: c.after.check.right >= c.before.check.right });
    rows.push({ label: "Examples fixed", value: `${c.fixed.length}` });
    rows.push({ label: "Examples broken", value: `${c.broke.length}`, ok: c.broke.length === 0 });
  }
  if (c.short) rows.push({ label: "Judge unavailable", value: `${c.short.graded}/${c.short.of} graded`, ok: false });
  if (c.manipulation) rows.push({
    label: "Manipulation resisted", value: `${c.manipulation.resisted}/${c.manipulation.n}`, ok: c.manipulation.resisted === c.manipulation.n,
    title: c.manipulation.resisted < c.manipulation.n ? `Scored ${c.manipulation.worst.score.toFixed(2)} with: ${c.manipulation.worst.claim}` : undefined,
  });
  if (c.calls) {
    rows.push({ label: "Agent calls passing", value: `${c.calls.pass_before}/${c.calls.n} → ${c.calls.pass_after}/${c.calls.n}` });
    rows.push({ label: "Mean score", value: `${c.calls.mean_before.toFixed(2)} → ${c.calls.mean_after.toFixed(2)}` });
  }
  return <section aria-label="Checks" className="min-w-0">
    <h3 className={sectionTitle}>Checks</h3>
    <dl className="m-0 mt-1.5 divide-y divide-border rounded-sm border border-border text-[12px]">
      {rows.map((r) => (
        <div key={r.label} title={r.title} className="flex items-center gap-2 px-2 py-1">
          <dt className="min-w-0 flex-1 text-muted-foreground">{r.label}</dt>
          <dd className="m-0 whitespace-nowrap tabular-nums">{r.value}</dd>
          <span className="flex w-3.5 justify-end">
            {r.ok === true && <Check aria-label="Passed" className="size-3.5 text-emerald-600" />}
            {r.ok === false && <X aria-label="Failed" className="size-3.5 text-destructive" />}
          </span>
        </div>
      ))}
    </dl>
  </section>;
}

// ── The evidence ─────────────────────────────────────────────────────────

const scores = (f: EvalFlip) => `${f.before.toFixed(2)} → ${f.after.toFixed(2)}`;

function Examples({ evalId, proposal: p }: { evalId: string; proposal: EvalProposal }) {
  const c = p.checks;
  if (!c) return null;
  const flipped = new Set([...c.fixed, ...c.broke].map((f) => f.id));
  const groups: { title: string; rows: { example: EvalChangeExample; flip?: EvalFlip }[] }[] = [
    { title: "Broken", rows: c.broke.map((f) => ({ example: p.examples[f.id], flip: f })) },
    { title: "Fixed", rows: c.fixed.map((f) => ({ example: p.examples[f.id], flip: f })) },
    { title: `New since v${p.base}`, rows: c.evidence.filter((id) => !flipped.has(id)).map((id) => ({ example: p.examples[id] })) },
  ].map((g) => ({ ...g, rows: g.rows.filter((r) => r.example) })).filter((g) => g.rows.length > 0);
  if (groups.length === 0) return null;
  return <section aria-label="Examples" className="space-y-2">
    {groups.map((g) => <div key={g.title}>
      <h3 className={sectionTitle}>{g.title} <span className="tabular-nums">{g.rows.length}</span></h3>
      <ul className="m-0 mt-1.5 list-none divide-y divide-border rounded-sm border border-border p-0">
        {g.rows.map(({ example: e, flip }) => (
          <li key={e.id}>
            <Link href={`/reward-models/evals/${evalId}/examples/${e.id}`} className="flex items-center gap-2.5 px-2 py-1.5 text-[12px] text-foreground no-underline hover:bg-surface/40">
              <span className={cn("w-8 shrink-0 font-medium", e.label === "good" ? "text-emerald-700 dark:text-emerald-400" : "text-red-700 dark:text-red-400")}>{e.label === "good" ? "Good" : "Bad"}</span>
              <Snippet snippet={e} thumb={evalExampleFilePath(evalId, e.id, 0)} note={e.note} />
              <span className="w-14 whitespace-nowrap text-muted-foreground">{e.held_out ? "Held out" : ""}</span>
              {flip && <span className="whitespace-nowrap tabular-nums">{scores(flip)}</span>}
              <span className="whitespace-nowrap text-muted-foreground">{[e.added_by_name, e.caller].filter(Boolean).join(", ")}</span>
              <time className="w-14 whitespace-nowrap text-right text-muted-foreground" dateTime={e.created_at}>{relativeTime(e.created_at)}</time>
            </Link>
          </li>
        ))}
      </ul>
    </div>)}
  </section>;
}

function CallList({ proposal: p }: { proposal: EvalProposal }) {
  const rows = (p.checks?.calls?.changed ?? []).map((f) => ({ flip: f, call: p.calls[f.id] })).filter((r): r is { flip: EvalFlip; call: EvalChangeCall } => !!r.call);
  if (rows.length === 0) return null;
  const verdict = (score: number) => (score >= 0.5 ? "Pass" : "Fail");
  return <section aria-label="Agent calls">
    <h3 className={sectionTitle}>Agent calls that change <span className="tabular-nums">{rows.length}</span></h3>
    <ul className="m-0 mt-1.5 list-none divide-y divide-border rounded-sm border border-border p-0">
      {rows.map(({ flip, call }) => (
        <li key={call.id} className="flex items-center gap-2.5 px-2 py-1.5 text-[12px]">
          <span className={cn("w-16 shrink-0 whitespace-nowrap font-medium", flip.after >= 0.5 ? "text-emerald-700 dark:text-emerald-400" : "text-red-700 dark:text-red-400")}>{verdict(flip.before)} → {verdict(flip.after)}</span>
          <Snippet snippet={call} />
          <span className="whitespace-nowrap tabular-nums">{scores(flip)}</span>
          <span className="whitespace-nowrap text-muted-foreground">{call.caller || "unknown caller"}</span>
          <time className="w-14 whitespace-nowrap text-right text-muted-foreground" dateTime={call.created_at}>{relativeTime(call.created_at)}</time>
        </li>
      ))}
    </ul>
  </section>;
}

/** An example or a call in one line: its image if it has one, else the start of its text. */
function Snippet({ snippet, thumb, note }: { snippet: { name: string; asked: string; text: string; files: { name: string; content_type: string }[] }; thumb?: string; note?: string }) {
  const image = thumb && snippet.files[0]?.content_type.startsWith("image/");
  const text = snippet.text || snippet.asked || snippet.files[0]?.name || snippet.name;
  return <span className="flex min-w-0 flex-1 items-center gap-2">
    {image && <FileThumb path={thumb} alt={snippet.files[0].name} zoom={false} className="size-7 shrink-0" />}
    <span className="min-w-0 flex-1 truncate">{text}{note && <span className="ml-2 text-muted-foreground">{note}</span>}</span>
  </span>;
}

// ── The decision ─────────────────────────────────────────────────────────

function Decide({ proposal: p, onDecide }: { proposal: EvalProposal; onDecide: (decision: Decision, note: string) => Promise<void> }) {
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState<Decision | "">("");
  const [error, setError] = useState("");
  const decide = async (decision: Decision) => {
    setBusy(decision); setError("");
    try { await onDecide(decision, note.trim()); } catch (e) { setError(errorMessage(e)); setBusy(""); }
  };
  return <div className="space-y-1.5 border-t border-border pt-3">
    <div className="flex flex-wrap items-center gap-1.5">
      <input value={note} onChange={(e) => setNote(e.target.value)} maxLength={2000} placeholder="Note" aria-label="Note"
        className="h-6 min-w-40 flex-1 rounded border border-border bg-background px-2 text-[12px] outline-none focus:border-foreground/40" />
      {!p.stale && (p.passed === false
        ? <button type="button" disabled={!!busy} onClick={() => void decide("approve")} className={buttonClass}>Approve anyway</button>
        : <button type="button" disabled={!!busy || p.passed === null} onClick={() => void decide("approve")}
          className="h-6 rounded bg-foreground px-2 text-[12px] text-background disabled:opacity-50">Approve</button>)}
      <button type="button" disabled={!!busy} onClick={() => void decide("reject")} className={buttonClass}>Reject</button>
    </div>
    {error && <p role="alert" className="m-0 text-[12px] text-destructive">{error}</p>}
  </div>;
}
