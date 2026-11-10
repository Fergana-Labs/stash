"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import type { ReactNode } from "react";
import { ArrowLeft, Check, ChevronDown, GitMerge, GitPullRequest, GitPullRequestClosed, Loader2, MessageSquare, Search, X } from "lucide-react";
import { cn } from "@/lib/utils";
import { EvalPageFrame, evalInputClass } from "@/components/evals/eval-ui";
import { errorMessage, relativeTime } from "@/components/reward-models/rm-text";
import { ChecksMark, changeState, changeTitle } from "./EvalChanges";
import FileThumb from "./FileThumb";
import {
  evalChanges, evalComment, evalDecide, evalExampleFilePath, evalGet,
  type EvalChangeCall, type EvalChangeExample, type EvalComment, type EvalFlip, type EvalProposal, type EvalTally, type EvalTrait,
} from "@/lib/evals-api";

type Decision = "approve" | "reject";
type Tab = "conversation" | "rubric" | "checks";
const TABS: Tab[] = ["conversation", "rubric", "checks"];

const SCORING = { mean: "Average", lowest: "Lowest trait" };
const STATE = {
  open: { label: "Open", icon: GitPullRequest, tone: "text-emerald-700 dark:text-emerald-400" },
  merged: { label: "Merged", icon: GitMerge, tone: "text-violet-700 dark:text-violet-400" },
  closed: { label: "Closed", icon: GitPullRequestClosed, tone: "text-red-700 dark:text-red-400" },
};
const chipClass = "rounded bg-brand-50 px-1.5 py-px font-mono text-[11px] text-brand-700 dark:bg-brand-600/15 dark:text-brand-300";
const sectionTitle = "m-0 text-[11px] font-medium uppercase tracking-wide text-muted-foreground";
const buttonClass = "h-7 rounded border border-border px-2.5 text-[12px] hover:bg-surface disabled:opacity-50";
const primaryClass = "h-7 rounded bg-foreground px-2.5 text-[12px] text-background disabled:opacity-50";

/** One proposed rubric change on its own page, the way a pull request has one: loads the
 * eval's changes, shows the one with this number, and checks again while its checks run. */
export default function EvalChange({ evalId, number, initialTab }: { evalId: string; number: number; initialTab?: string }) {
  const [proposals, setProposals] = useState<EvalProposal[] | null>(null);
  const [evalName, setEvalName] = useState("");
  const [error, setError] = useState("");
  const load = useCallback(async () => {
    try { setProposals((await evalChanges(evalId)).proposals); setError(""); } catch (e) { setError(errorMessage(e)); }
  }, [evalId]);
  useEffect(() => {
    void load();
    evalGet(evalId).then((e) => setEvalName(e.name)).catch(() => undefined);
  }, [evalId, load]);
  const proposal = proposals?.find((p) => p.number === number);
  const checking = !!proposal && proposal.status === "open" && proposal.checks === null;
  useEffect(() => {
    if (!checking) return;
    const timer = setInterval(() => void load(), 4000);
    return () => clearInterval(timer);
  }, [checking, load]);

  const back = <Link href={`/reward-models/evals/${evalId}?tab=changes`} className="inline-flex items-center gap-1 text-[12px] text-muted-foreground hover:text-foreground">
    <ArrowLeft className="size-3.5" aria-hidden />{evalName || "Changes"}
  </Link>;
  if (!proposal) return <EvalPageFrame>{back}
    <p role={error || proposals ? "alert" : "status"} className="mt-4 text-sm text-muted-foreground">{error || (proposals ? "Change not found" : "Loading")}</p>
  </EvalPageFrame>;
  return <EvalPageFrame>
    {back}
    <ChangeView evalId={evalId} proposal={proposal} initialTab={initialTab}
      onDecide={async (decision, note) => setProposals((await evalDecide(evalId, proposal.id, decision, note)).proposals)}
      onComment={async (body, trait) => setProposals((await evalComment(evalId, proposal.id, body, trait)).proposals)} />
  </EvalPageFrame>;
}

/** The change's name as a branch would have one: the rubric is what a pull request's base
 * branch is, and stays "rubric" from version to version; the change is the branch merged
 * into it, called by its own name or, without one, after its first edit ("add-stripes"). */
export function changeBranch(p: EvalProposal): string {
  if (p.name) return p.name;
  const first = p.changes[0];
  const words = first ? `${first.kind} ${first.trait}` : `change ${p.number}`;
  return words.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "") || `change-${p.number}`;
}

/** A proposed change as a pull request on the rubric: a conversation that opens with how the
 * agent fares under the proposed rubric and ends in a merge or a close, the rubric before and
 * after, and the checks that measured it. */
export function ChangeView({ evalId, proposal: p, initialTab, onDecide, onComment }: {
  evalId: string;
  proposal: EvalProposal;
  initialTab?: string;
  onDecide: (decision: Decision, note: string) => Promise<void>;
  onComment: (body: string, trait: string) => Promise<void>;
}) {
  const [tab, setTab] = useState<Tab>(TABS.includes(initialTab as Tab) ? (initialTab as Tab) : "conversation");
  const state = STATE[changeState(p)];
  const Icon = state.icon;
  const diff = rubricDiff(p);
  const merged = p.status === "approved";
  const branch = changeBranch(p);
  const tabs: { key: Tab; label: string; extra?: ReactNode }[] = [
    { key: "conversation", label: "Conversation", extra: p.comments.length > 0 ? <span className="tabular-nums text-muted-foreground">{p.comments.length}</span> : null },
    { key: "rubric", label: "Rubric changes", extra: <span className="tabular-nums text-muted-foreground">{diff.count}</span> },
    { key: "checks", label: "Checks", extra: <ChecksMark proposal={p} /> },
  ];
  return <article aria-label={`Change ${p.number}`} className="text-[13px]">
    <h1 className="mt-2 mb-1 text-[16px] font-semibold tracking-tight">{changeTitle(p.changes)} <span className="font-normal tabular-nums text-muted-foreground">#{p.number}</span></h1>
    <div className="flex flex-wrap items-center gap-x-2.5 text-[12px] text-muted-foreground">
      <span className={cn("inline-flex items-center gap-1 font-medium", state.tone)}><Icon aria-hidden className="size-3.5" />{state.label}</span>
      {p.stale && <span>Out of date</span>}
      <span><span className="font-medium text-foreground">{merged ? p.decided_by ?? "Unknown" : p.opened_by ?? "Unknown"}</span> {merged ? "merged" : p.status === "open" ? "wants to merge" : "wanted to merge"} {diff.count} {diff.count === 1 ? "edit" : "edits"} into</span>
      <span aria-label={`rubric from ${branch}`} className="inline-flex items-center gap-1.5">
        <span className={chipClass}>rubric</span>
        <ArrowLeft aria-hidden className="size-3.5" />
        <span className={chipClass}>{branch}</span>
      </span>
      <time dateTime={merged && p.decided_at ? p.decided_at : p.created_at}>{relativeTime(merged && p.decided_at ? p.decided_at : p.created_at)}</time>
    </div>
    <nav aria-label="Change sections" className="mt-3 mb-3 flex gap-1 border-b border-border pb-1.5">
      {tabs.map((t) => (
        <button key={t.key} type="button" aria-current={tab === t.key ? "page" : undefined} onClick={() => setTab(t.key)}
          className={cn("flex h-6 items-center gap-1.5 rounded-sm px-2 text-[12px]", tab === t.key ? "bg-surface font-medium text-foreground" : "text-muted-foreground hover:text-foreground")}>
          {t.label}{t.extra}
        </button>
      ))}
    </nav>
    <div className="min-w-0">
      {tab === "conversation" && <Conversation proposal={p} onDecide={onDecide} onComment={onComment} />}
      {tab === "rubric" && <RubricDiff proposal={p} diff={diff} onComment={onComment} />}
      {tab === "checks" && <div className="min-w-0 space-y-3">
        <Checks proposal={p} />
        <Flipped evalId={evalId} proposal={p} />
      </div>}
    </div>
  </article>;
}

// ── The conversation ─────────────────────────────────────────────────────

function Conversation({ proposal: p, onDecide, onComment }: {
  proposal: EvalProposal;
  onDecide: (decision: Decision, note: string) => Promise<void>;
  onComment: (body: string, trait: string) => Promise<void>;
}) {
  const state = changeState(p);
  // Comments made before the decision come before it; the rest follow.
  const before = p.comments.filter((c) => !p.decided_at || c.created_at <= p.decided_at);
  const after = p.comments.filter((c) => p.decided_at && c.created_at > p.decided_at);
  const calls = p.checks?.calls;
  return <section aria-label="Conversation" className="min-w-0 space-y-2">
    <Entry who={p.opened_by ?? "Unknown"} what="opened" at={p.created_at}>
      {p.checks?.summary && <p className="m-0">{p.checks.summary}</p>}
      {calls && !p.checks?.summary && <p className="m-0 tabular-nums">{calls.pass_after} of {calls.n} agent calls pass, {calls.pass_before} before</p>}
      <CallList proposal={p} />
    </Entry>
    {before.map((c) => <CommentEntry key={c.id} comment={c} />)}
    {state !== "open" && p.decided_at && <Entry who={p.decided_by ?? "Someone"} at={p.decided_at}
      what={state === "merged" ? `merged${p.version ? ` as rubric v${p.version}` : ""}` : "closed"}
      icon={state === "merged" ? <GitMerge aria-hidden className={cn("size-3.5", STATE.merged.tone)} /> : <GitPullRequestClosed aria-hidden className={cn("size-3.5", STATE.closed.tone)} />}>
      {p.note && <p className="m-0 whitespace-pre-wrap">{p.note}</p>}
    </Entry>}
    {after.map((c) => <CommentEntry key={c.id} comment={c} />)}
    <Composer proposal={p} onDecide={onDecide} onComment={(body) => onComment(body, "")} />
  </section>;
}

/** One step of the conversation: who did what and when, and what they said. */
function Entry({ who, what, at, about, icon, children }: { who: string; what: string; at: string; about?: string; icon?: ReactNode; children?: ReactNode }) {
  const body = Array.isArray(children) ? children.some(Boolean) : !!children;
  return <div className="rounded border border-border">
    <div className={cn("flex items-center gap-1.5 px-3 py-1.5 text-[12px]", body && "border-b border-border bg-surface/40")}>
      {icon}
      <span className="font-medium">{who}</span>
      <span className="text-muted-foreground">{what}</span>
      {about && <span className="min-w-0 truncate text-muted-foreground">on {about}</span>}
      <time className="ml-auto whitespace-nowrap text-muted-foreground" dateTime={at}>{relativeTime(at)}</time>
    </div>
    {body && <div className="px-3 py-2">{children}</div>}
  </div>;
}

function CommentEntry({ comment: c }: { comment: EvalComment }) {
  return <Entry who={c.author ?? "Someone"} what="commented" about={c.trait || undefined} at={c.created_at}>
    <p className="m-0 whitespace-pre-wrap">{c.body}</p>
  </Entry>;
}

/** Where the change is commented on, and while it is open, merged into the rubric or closed.
 * What is typed goes with whichever button is pressed. */
function Composer({ proposal: p, onDecide, onComment }: {
  proposal: EvalProposal;
  onDecide: (decision: Decision, note: string) => Promise<void>;
  onComment: (body: string) => Promise<void>;
}) {
  const [text, setText] = useState("");
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");
  const run = async (what: string, action: () => Promise<void>) => {
    setBusy(what); setError("");
    try { await action(); setText(""); } catch (e) { setError(errorMessage(e)); }
    setBusy("");
  };
  const open = p.status === "open";
  return <div className="space-y-1.5 rounded border border-border p-2">
    {open && <div className="flex items-center gap-1.5 px-1 text-[12px]">
      <ChecksMark proposal={p} />
      <span>{p.stale ? "Out of date" : p.passed === null ? "Checking" : p.passed ? "Checks passed" : "Checks failed"}</span>
    </div>}
    <textarea value={text} onChange={(e) => setText(e.target.value)} rows={2} maxLength={2000} placeholder="Comment" aria-label="Comment" className={evalInputClass} />
    <div className="flex flex-wrap items-center justify-end gap-1.5">
      {error && <p role="alert" className="m-0 mr-auto text-[12px] text-destructive">{error}</p>}
      {open && <button type="button" disabled={!!busy} onClick={() => void run("reject", () => onDecide("reject", text.trim()))} className={buttonClass}>Close</button>}
      <button type="button" disabled={!!busy || !text.trim()} onClick={() => void run("comment", () => onComment(text.trim()))} className={buttonClass}>Comment</button>
      {open && !p.stale && (p.passed === false
        ? <button type="button" disabled={!!busy} onClick={() => void run("approve", () => onDecide("approve", text.trim()))} className={buttonClass}>Merge anyway</button>
        : <button type="button" disabled={!!busy || p.passed === null} onClick={() => void run("approve", () => onDecide("approve", text.trim()))} className={primaryClass}>Approve and merge</button>)}
    </div>
  </div>;
}

// ── The rubric, before and after ─────────────────────────────────────────

const key = (name: string) => name.trim().toLowerCase();
type Line = ["+" | "-", string, string];
interface Diffed { sign: "+" | "-" | "~"; name: string; why?: string; lines: Line[]; trait: boolean }

/** What the change does to the rubric, trait by trait, then its scoring rule and description. */
function rubricDiff(p: EvalProposal): { items: Diffed[]; general: string[]; unchanged: number; count: number } {
  const before = p.before?.traits ?? [];
  const old = new Map(before.map((t) => [key(t.name), t]));
  const now = new Map(p.traits.map((t) => [key(t.name), t]));
  const why = new Map(p.changes.filter((c) => c.trait).map((c) => [key(c.trait), c.why]));
  const changed = (a: EvalTrait, b: EvalTrait) => a.good !== b.good || a.bad !== b.bad;
  const items: Diffed[] = [];
  let untouched = 0;
  for (const t of p.traits) {
    const was = old.get(key(t.name));
    if (!was) items.push({ sign: "+", name: t.name, why: why.get(key(t.name)), trait: true, lines: [["+", "Good", t.good], ["+", "Bad", t.bad]] });
    else if (changed(was, t)) {
      const lines: Line[] = [];
      if (was.good !== t.good) lines.push(["-", "Good", was.good], ["+", "Good", t.good]);
      if (was.bad !== t.bad) lines.push(["-", "Bad", was.bad], ["+", "Bad", t.bad]);
      items.push({ sign: "~", name: t.name, why: why.get(key(t.name)), trait: true, lines });
    } else untouched += 1;
  }
  for (const t of before) if (!now.has(key(t.name))) items.push({ sign: "-", name: t.name, why: why.get(key(t.name)), trait: true, lines: [["-", "Good", t.good], ["-", "Bad", t.bad]] });
  if (p.before && p.before.scoring !== p.scoring) items.push({ sign: "~", name: "Scored by", why: p.changes.find((c) => c.kind === "scoring")?.why, trait: false, lines: [["-", "", SCORING[p.before.scoring]], ["+", "", SCORING[p.scoring]]] });
  if (p.before && p.before.instructions !== p.instructions) items.push({ sign: "~", name: "Description", trait: false, lines: [["-", "", p.before.instructions], ["+", "", p.instructions]] });
  const general = p.changes.filter((c) => !c.trait && c.why && c.kind !== "description").map((c) => c.why);
  return { items, general, unchanged: untouched, count: items.length };
}

function RubricDiff({ proposal: p, diff, onComment }: { proposal: EvalProposal; diff: ReturnType<typeof rubricDiff>; onComment: (body: string, trait: string) => Promise<void> }) {
  return <section aria-label="Rubric changes" className="min-w-0 space-y-1.5">
    {diff.general.map((text, i) => <p key={i} className="m-0 text-[12px] text-muted-foreground">{text}</p>)}
    {diff.items.map((d) => <TraitDiff key={d.name} diff={d}
      comments={d.trait ? p.comments.filter((c) => key(c.trait) === key(d.name)) : []}
      onComment={d.trait ? (body) => onComment(body, d.name) : undefined} />)}
    {diff.unchanged > 0 && <p className="m-0 text-[12px] text-muted-foreground">{diff.unchanged} {diff.unchanged === 1 ? "trait" : "traits"} unchanged</p>}
  </section>;
}

function TraitDiff({ diff: d, comments, onComment }: { diff: Diffed; comments: EvalComment[]; onComment?: (body: string) => Promise<void> }) {
  const [writing, setWriting] = useState(false);
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const send = async () => {
    if (!onComment || !text.trim()) return;
    setBusy(true); setError("");
    try { await onComment(text.trim()); setText(""); setWriting(false); } catch (e) { setError(errorMessage(e)); }
    setBusy(false);
  };
  return <div className="overflow-hidden rounded-sm border border-border">
    <div className="flex items-start gap-2 px-2 py-1">
      <span aria-hidden className={cn("w-3 font-mono text-[12px] leading-5", d.sign === "+" ? "text-emerald-700 dark:text-emerald-400" : d.sign === "-" ? "text-red-700 dark:text-red-400" : "text-muted-foreground")}>{d.sign}</span>
      <span className="whitespace-nowrap font-medium leading-5">{d.name}</span>
      <span className="min-w-0 flex-1 text-[12px] leading-5 text-muted-foreground">{d.why}</span>
      {onComment && <button type="button" aria-label={`Comment on ${d.name}`} title="Comment" onClick={() => setWriting(!writing)}
        className="flex size-5 shrink-0 items-center justify-center rounded-sm text-muted-foreground hover:bg-surface hover:text-foreground">
        <MessageSquare aria-hidden className="size-3.5" />
      </button>}
    </div>
    {d.lines.filter(([, , text]) => text).map(([kind, label, text], i) => (
      <div key={i} className={cn("flex gap-2 border-l-2 px-2 py-0.5 text-[12px]", kind === "+" ? "border-l-emerald-600" : "border-l-red-500")}>
        <span aria-hidden className={cn("w-3 font-mono", kind === "+" ? "text-emerald-700 dark:text-emerald-400" : "text-red-700 dark:text-red-400")}>{kind}</span>
        {label && <span className="w-8 shrink-0 text-muted-foreground">{label}</span>}
        <span className={cn("min-w-0 flex-1", kind === "-" && "text-muted-foreground")}>{text}</span>
      </div>
    ))}
    {comments.map((c) => (
      <div key={c.id} className="border-t border-border px-2 py-1.5 text-[12px]">
        <div className="flex items-baseline gap-1.5">
          <span className="font-medium">{c.author ?? "Someone"}</span>
          <time className="text-muted-foreground" dateTime={c.created_at}>{relativeTime(c.created_at)}</time>
        </div>
        <p className="m-0 whitespace-pre-wrap">{c.body}</p>
      </div>
    ))}
    {writing && <div className="flex flex-wrap items-center gap-1.5 border-t border-border p-1.5">
      <input autoFocus value={text} onChange={(e) => setText(e.target.value)} onKeyDown={(e) => { if (e.key === "Enter") void send(); }} maxLength={2000}
        placeholder="Comment" aria-label={`Comment on ${d.name}`}
        className="h-6 min-w-40 flex-1 rounded border border-border bg-background px-2 text-[12px] outline-none focus:border-foreground/40" />
      <button type="button" disabled={busy || !text.trim()} onClick={() => void send()} className="h-6 rounded border border-border px-2 text-[12px] hover:bg-surface disabled:opacity-50">Comment</button>
      {error && <p role="alert" className="m-0 w-full text-[12px] text-destructive">{error}</p>}
    </div>}
  </div>;
}

// ── Checks ───────────────────────────────────────────────────────────────

const ratio = (t: EvalTally) => `${t.right}/${t.n}`;

/** What was measured about the proposed rubric itself before anyone decides, beside the same
 * measure for the rubric in use: how well each agrees with the person's labels, which labeled
 * examples the change sets right or wrong, and whether it can be talked into a good score. */
function Checks({ proposal: p }: { proposal: EvalProposal }) {
  const c = p.checks;
  if (!c) return <section aria-label="Checks">
    <p role="status" className="m-0 flex items-center gap-1 text-[12px] text-muted-foreground"><Loader2 className="size-3 animate-spin" />Checking</p></section>;
  // before: the value for the rubric in use; after: for the proposed one.
  const rows: { label: string; before?: string; after: string; ok?: boolean; title?: string }[] = [];
  const { before: qb, after: qa } = p.quality;
  if (qa) rows.push({ label: "Rubric quality", before: qb ? `${qb.score}` : undefined, after: `${qa.score}`, ok: qb ? qa.score >= qb.score : undefined });
  if (c.before && c.after) {
    if (c.after.fit.n > 0) rows.push({ label: "Agrees with your labels", before: ratio(c.before.fit), after: ratio(c.after.fit), ok: c.after.fit.right >= c.before.fit.right });
    if (c.after.check.n > 0) rows.push({ label: "Agrees with held-out labels", before: ratio(c.before.check), after: ratio(c.after.check), ok: c.after.check.right >= c.before.check.right });
    rows.push({ label: "Labeled examples fixed", after: `${c.fixed.length}` });
    rows.push({ label: "Labeled examples broken", after: `${c.broke.length}`, ok: c.broke.length === 0 });
  }
  if (c.short) rows.push({ label: "Judge unavailable", after: `${c.short.graded}/${c.short.of} graded`, ok: false });
  if (c.manipulation) rows.push({
    label: "Manipulation attempts resisted", after: `${c.manipulation.resisted}/${c.manipulation.n}`, ok: c.manipulation.resisted === c.manipulation.n,
    title: c.manipulation.resisted < c.manipulation.n ? `Scored ${c.manipulation.worst.score.toFixed(2)} with: ${c.manipulation.worst.claim}` : undefined,
  });
  const column = "w-px whitespace-nowrap pl-3 text-right tabular-nums";
  return <section aria-label="Checks" className="min-w-0">
    <table className="w-full border-collapse text-[12px]">
      <thead>
        <tr className="text-left text-[11px] uppercase tracking-wide text-muted-foreground">
          <th scope="col" className="pb-1 font-medium">Checks</th>
          <th scope="col" className="whitespace-nowrap pb-1 pl-3 text-right font-normal normal-case tracking-normal"><span className={chipClass}>rubric</span></th>
          <th scope="col" className="whitespace-nowrap pb-1 pl-3 text-right font-normal normal-case tracking-normal"><span className={chipClass}>{changeBranch(p)}</span></th>
          <th className="w-px pl-2" />
        </tr>
      </thead>
      <tbody>
        {rows.map((r) => (
          <tr key={r.label} title={r.title} className="border-t border-border">
            <th scope="row" className="py-1.5 pr-3 text-left font-normal">{r.label}</th>
            <td className={cn(column, "py-1.5 text-muted-foreground")}>{r.before}</td>
            <td className={cn(column, "py-1.5")}>{r.after}</td>
            <td className="w-px py-1.5 pl-2">
              <span className="flex w-3.5 justify-end">
                {r.ok === true && <Check aria-label="Passed" className="size-3.5 text-emerald-600" />}
                {r.ok === false && <X aria-label="Failed" className="size-3.5 text-destructive" />}
              </span>
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  </section>;
}

// ── What the checks point at ─────────────────────────────────────────────

/** The score under the proposed rubric, then the one it had. */
const scores = (f: EvalFlip) => <span className="whitespace-nowrap tabular-nums">{f.after.toFixed(2)} <span className="text-muted-foreground">was {f.before.toFixed(2)}</span></span>;

/** The labeled examples whose verdict the change sets wrong, the ones it sets right, and the
 * rest of the examples added since the version it was proposed on. */
function Flipped({ evalId, proposal: p }: { evalId: string; proposal: EvalProposal }) {
  const c = p.checks;
  if (!c) return null;
  const flipped = new Set([...c.fixed, ...c.broke].map((f) => f.id));
  const groups: { title: string; rows: { example: EvalChangeExample; flip?: EvalFlip }[] }[] = [
    { title: "Broken", rows: c.broke.map((f) => ({ example: p.examples[f.id], flip: f })) },
    { title: "Fixed", rows: c.fixed.map((f) => ({ example: p.examples[f.id], flip: f })) },
    { title: `New since v${p.base}`, rows: c.evidence.filter((id) => !flipped.has(id)).map((id) => ({ example: p.examples[id] })) },
  ].map((g) => ({ ...g, rows: g.rows.filter((r) => r.example) })).filter((g) => g.rows.length > 0);
  if (groups.length === 0) return null;
  return <section aria-label="Examples" className="min-w-0 space-y-2">
    {groups.map((g) => <div key={g.title}>
      <h3 className={sectionTitle}>{g.title} <span className="tabular-nums">{g.rows.length}</span></h3>
      <ExampleRows evalId={evalId} rows={g.rows} />
    </div>)}
  </section>;
}

function ExampleRows({ evalId, rows }: { evalId: string; rows: { example: EvalChangeExample; flip?: EvalFlip }[] }) {
  return <ul className="m-0 mt-1.5 list-none divide-y divide-border rounded-sm border border-border p-0">
    {rows.map(({ example: e, flip }) => (
      <li key={e.id}>
        <Link href={`/reward-models/evals/${evalId}/examples/${e.id}`} className="flex items-center gap-2.5 px-2 py-1.5 text-[12px] text-foreground no-underline hover:bg-surface/40">
          <span className={cn("w-8 shrink-0 font-medium", e.label === "good" ? "text-emerald-700 dark:text-emerald-400" : "text-red-700 dark:text-red-400")}>{e.label === "good" ? "Good" : "Bad"}</span>
          <Snippet snippet={e} thumb={evalExampleFilePath(evalId, e.id, 0)} note={e.note} />
          {e.held_out && <span className="whitespace-nowrap text-muted-foreground">Held out</span>}
          {flip && scores(flip)}
          <span className="whitespace-nowrap text-muted-foreground">{[e.added_by_name, e.caller].filter(Boolean).join(", ")}</span>
          <time className="w-14 whitespace-nowrap text-right text-muted-foreground" dateTime={e.created_at}>{relativeTime(e.created_at)}</time>
        </Link>
      </li>
    ))}
  </ul>;
}

/** The agent's recent calls as evals of the change, searchable by name: each one's name (what the agent
 * was asked, else the start of what it wrote), the score it got under the rubric in use, and
 * its score under the proposed rubric, in columns headed as the page header names the two:
 * "rubric" and the change's own name. A last column gives how far the score moved, and the
 * table is sorted by it, largest move first; its heading is marked as the sort. */
/** How far a score moved, signed: "-0.88", "+0.03", "0.00". */
function delta(f: EvalFlip): string {
  const moved = f.after - f.before;
  return Math.abs(moved) < 0.005 ? "0.00" : `${moved > 0 ? "+" : "-"}${Math.abs(moved).toFixed(2)}`;
}

function CallList({ proposal: p }: { proposal: EvalProposal }) {
  const [query, setQuery] = useState("");
  const all = (p.checks?.calls?.calls ?? []).map((f) => ({ flip: f, call: p.calls[f.id] })).filter((r): r is { flip: EvalFlip; call: EvalChangeCall } => !!r.call)
    .map((r) => ({ ...r, name: r.call.name || r.call.asked || r.call.text.split("\n")[0] || r.call.files[0]?.name || "" }))
    .sort((a, b) => Math.abs(b.flip.after - b.flip.before) - Math.abs(a.flip.after - a.flip.before));
  if (all.length === 0) return null;
  const wanted = query.trim().toLowerCase();
  const rows = wanted ? all.filter((r) => r.name.toLowerCase().includes(wanted)) : all;
  const column = "w-px whitespace-nowrap pl-3 text-right tabular-nums";
  return <table aria-label="Evals" className="mt-2 w-full border-collapse text-[12px] first:mt-0">
    <thead>
      <tr className="text-left text-[11px] uppercase tracking-wide text-muted-foreground">
        <th scope="col" className="pb-1 font-medium">
          <span className="flex items-center gap-2">
            Evals
            <span className="relative flex items-center">
              <Search aria-hidden className="pointer-events-none absolute left-1.5 size-3" />
              <input type="search" value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Search" aria-label="Search evals"
                className="h-6 w-44 rounded border border-border bg-background pr-2 pl-6 text-[12px] font-normal normal-case tracking-normal text-foreground outline-none focus:border-foreground/40" />
            </span>
          </span>
        </th>
        <th scope="col" className="whitespace-nowrap pb-1 pl-3 text-right font-normal normal-case tracking-normal"><span className={chipClass}>rubric</span></th>
        <th scope="col" className="whitespace-nowrap pb-1 pl-3 text-right font-normal normal-case tracking-normal"><span className={chipClass}>{changeBranch(p)}</span></th>
        <th scope="col" aria-sort="descending" className={cn(column, "pb-1 font-medium text-foreground")}>
          <span className="inline-flex items-center gap-0.5">Change<ChevronDown aria-hidden className="size-3" /></span>
        </th>
      </tr>
    </thead>
    <tbody>
      {rows.map(({ flip, call, name }) => (
        <tr key={call.id} title={flip.low ? `${flip.low.trait}: ${flip.low.why}` : undefined} className="border-t border-border">
          <td className="max-w-0 truncate py-1.5 pr-3">{name}</td>
          <td className={cn(column, "py-1.5 text-muted-foreground")}>{flip.before.toFixed(2)}</td>
          <td className={cn(column, "py-1.5")}>{flip.after.toFixed(2)}</td>
          <td className={cn(column, "py-1.5 font-medium", Math.abs(flip.after - flip.before) < 0.005 && "font-normal text-muted-foreground")}>{delta(flip)}</td>
        </tr>
      ))}
      {rows.length === 0 && <tr className="border-t border-border"><td colSpan={4} className="py-1.5 text-muted-foreground">No evals match</td></tr>}
    </tbody>
  </table>;
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
