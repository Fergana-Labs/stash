"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import type { ReactNode } from "react";
import { ArrowLeft, ChevronDown, ChevronUp, GitMerge, GitPullRequest, GitPullRequestClosed, Search } from "lucide-react";
import { cn } from "@/lib/utils";
import { EvalPageFrame } from "@/components/evals/eval-ui";
import { diffLines, errorMessage, relativeTime } from "@/components/reward-models/rm-text";
import { changeState, changeTitle } from "./EvalChanges";
import {
  evalChanges, evalDecide, evalGet,
  type EvalChangeCall, type EvalChangeExample, type EvalComment, type EvalFlip, type EvalProposal, type EvalTrait,
} from "@/lib/evals-api";

type Decision = "approve" | "reject";
type Tab = "conversation" | "rubric" | "quality";
const TABS: Tab[] = ["conversation", "rubric", "quality"];

const SCORING = { mean: "Average", lowest: "Lowest trait" };
const STATE = {
  open: { label: "Open", icon: GitPullRequest, tone: "text-emerald-700 dark:text-emerald-400" },
  merged: { label: "Merged", icon: GitMerge, tone: "text-violet-700 dark:text-violet-400" },
  closed: { label: "Closed", icon: GitPullRequestClosed, tone: "text-red-700 dark:text-red-400" },
};
const chipClass = "rounded bg-brand-50 px-1.5 py-px font-[ui-monospace,SFMono-Regular,Menlo,monospace] text-[11px] text-brand-700 dark:bg-brand-600/15 dark:text-brand-300";
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
      onDecide={async (decision, note) => setProposals((await evalDecide(evalId, proposal.id, decision, note)).proposals)} />
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
 * agent fares under the proposed rubric and ends in a merge or a close, the rubric's diff, and
 * how the eval that grades its rubrics scored both. */
export function ChangeView({ evalId, proposal: p, initialTab, onDecide }: {
  evalId: string;
  proposal: EvalProposal;
  initialTab?: string;
  onDecide: (decision: Decision, note: string) => Promise<void>;
}) {
  const [tab, setTab] = useState<Tab>(TABS.includes(initialTab as Tab) ? (initialTab as Tab) : "conversation");
  const state = STATE[changeState(p)];
  const Icon = state.icon;
  const diff = rubricDiff(p);
  const merged = p.status === "approved";
  const branch = changeBranch(p);
  const quality = p.checks?.rubric_quality;
  const tabs: { key: Tab; label: string; extra?: ReactNode }[] = [
    { key: "conversation", label: "Conversation", extra: p.comments.length > 0 ? <span className="tabular-nums text-muted-foreground">{p.comments.length}</span> : null },
    { key: "rubric", label: "Diff", extra: <span className="tabular-nums text-muted-foreground">+{diff.added} -{diff.removed}</span> },
    ...(quality ? [{ key: "quality" as const, label: "Rubric quality", extra: <span className="tabular-nums text-muted-foreground">{quality.after.score.toFixed(2)}</span> }] : []),
  ];
  return <article aria-label={`Change ${p.number}`} className="text-[13px]">
    <h1 className="mt-2 mb-1 text-[16px] font-semibold tracking-tight">{changeTitle(p.changes)} <span className="font-normal tabular-nums text-muted-foreground">#{p.number}</span></h1>
    <div className="flex flex-wrap items-center gap-x-2.5 text-[12px] text-muted-foreground">
      <span className={cn("inline-flex items-center gap-1 font-medium", state.tone)}><Icon aria-hidden className="size-3.5" />{state.label}</span>
      {p.stale && <span>Out of date</span>}
      <span><span className="font-medium text-foreground">{merged ? p.decided_by ?? "Unknown" : p.opened_by ?? "Unknown"}</span> {merged ? "merged" : p.status === "open" ? "wants to merge" : "wanted to merge"} {p.changes.length} {p.changes.length === 1 ? "edit" : "edits"} into</span>
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
      {tab === "conversation" && <Conversation evalId={evalId} proposal={p} onDecide={onDecide} />}
      {tab === "rubric" && <RubricDiff diff={diff} />}
      {tab === "quality" && quality && <RubricQuality proposal={p} quality={quality} />}
    </div>
  </article>;
}

// ── The conversation ─────────────────────────────────────────────────────

function Conversation({ evalId, proposal: p, onDecide }: {
  evalId: string;
  proposal: EvalProposal;
  onDecide: (decision: Decision, note: string) => Promise<void>;
}) {
  const state = changeState(p);
  // Comments made before the decision come before it; the rest follow.
  const before = p.comments.filter((c) => !p.decided_at || c.created_at <= p.decided_at);
  const after = p.comments.filter((c) => p.decided_at && c.created_at > p.decided_at);
  const calls = p.checks?.calls;
  // The examples added since the rubric version the change was made on: what it answers.
  const evidence = (p.checks?.evidence ?? []).map((id) => p.examples[id]).filter(Boolean);
  const [hideSame, setHideSame] = useState(false);
  return <section aria-label="Conversation" className="min-w-0 space-y-2">
    <Entry who={p.opened_by ?? "Unknown"} what="opened" at={p.created_at}>
      <div className="flex items-start gap-3">
        <div className="min-w-0 flex-1">
          {p.checks?.summary && <p className="m-0">{p.checks.summary}</p>}
          {calls && !p.checks?.summary && <p className="m-0 tabular-nums">{calls.pass_after} of {calls.n} agent calls pass, {calls.pass_before} before</p>}
        </div>
        {calls?.calls.some(unchanged) && <button type="button" role="switch" aria-checked={hideSame} onClick={() => setHideSame(!hideSame)}
          className="flex shrink-0 items-center gap-1.5 text-[12px] text-muted-foreground hover:text-foreground">
          Hide unchanged
          <span aria-hidden className={cn("flex h-3.5 w-6 items-center rounded px-0.5 transition-colors", hideSame ? "bg-foreground" : "bg-border")}>
            <span className={cn("size-2.5 rounded-sm bg-background transition-transform", hideSame && "translate-x-2.5")} />
          </span>
        </button>}
      </div>
      {evidence.length > 0 && <div className="-mx-3 mt-2 border-t border-border px-3 pt-2">
        <Evidence evalId={evalId} examples={evidence} />
      </div>}
      {(calls?.calls.length ?? 0) > 0 && <div className="-mx-3 mt-2 border-t border-border px-3 pt-2">
        <CallList proposal={p} hideSame={hideSame} />
      </div>}
    </Entry>
    {before.map((c) => <CommentEntry key={c.id} comment={c} />)}
    {state !== "open" && p.decided_at && <Entry who={p.decided_by ?? "Someone"} at={p.decided_at}
      what={state === "merged" ? `merged${p.version ? ` as rubric v${p.version}` : ""}` : "closed"}
      icon={state === "merged" ? <GitMerge aria-hidden className={cn("size-3.5", STATE.merged.tone)} /> : <GitPullRequestClosed aria-hidden className={cn("size-3.5", STATE.closed.tone)} />}>
      {p.note && <p className="m-0 whitespace-pre-wrap">{p.note}</p>}
    </Entry>}
    {after.map((c) => <CommentEntry key={c.id} comment={c} />)}
    {p.status === "open" && <Decide proposal={p} onDecide={onDecide} />}
  </section>;
}

/** The examples a change answers: each one's label, what it is, the person's reason, who added
 * it and when. Each opens the example, which links to the trace step it was taken from. */
function Evidence({ evalId, examples }: { evalId: string; examples: EvalChangeExample[] }) {
  return <table aria-label="Examples" className="w-full border-collapse text-[12px]">
    <thead>
      <tr className="text-left text-[11px] uppercase tracking-wide text-muted-foreground">
        <th scope="col" colSpan={4} className="pb-2 font-medium">Examples <span className="tabular-nums">{examples.length}</span></th>
      </tr>
    </thead>
    <tbody>
      {examples.map((e) => (
        <tr key={e.id} className="relative border-t border-border hover:bg-surface/40">
          <td className={cn("w-px whitespace-nowrap py-1.5 pr-3 font-medium", e.label === "good" ? "text-emerald-700 dark:text-emerald-400" : "text-red-700 dark:text-red-400")}>{e.label === "good" ? "Good" : "Bad"}</td>
          <td className="max-w-0 truncate py-1.5 pr-3">
            <Link href={`/reward-models/evals/${evalId}/examples/${e.id}`} className="text-foreground no-underline after:absolute after:inset-0">{e.files[0]?.name || e.name || e.text.split("\n")[0] || e.asked}</Link>
            {e.note && <span className="ml-2 text-muted-foreground">{e.note}</span>}
          </td>
          <td className="w-px whitespace-nowrap py-1.5 pl-3 text-muted-foreground">{[e.added_by_name, e.caller].filter(Boolean).join(", ")}</td>
          <td className="w-px whitespace-nowrap py-1.5 pl-3 text-right text-muted-foreground"><time dateTime={e.created_at}>{relativeTime(e.created_at)}</time></td>
        </tr>
      ))}
    </tbody>
  </table>;
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

/** Where an open change is decided: close it, or approve it and merge it into the rubric.
 * One made on a version that is no longer current can only be closed. */
function Decide({ proposal: p, onDecide }: { proposal: EvalProposal; onDecide: (decision: Decision, note: string) => Promise<void> }) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const decide = async (decision: Decision) => {
    setBusy(true); setError("");
    try { await onDecide(decision, ""); } catch (e) { setError(errorMessage(e)); }
    setBusy(false);
  };
  return <div className="flex flex-wrap items-center justify-end gap-1.5">
    {error && <p role="alert" className="m-0 mr-auto text-[12px] text-destructive">{error}</p>}
    <button type="button" disabled={busy} onClick={() => void decide("reject")} className={buttonClass}>Close</button>
    {!p.stale && <button type="button" disabled={busy} onClick={() => void decide("approve")} className={primaryClass}>Approve and merge</button>}
  </div>;
}

// ── The rubric, before and after ─────────────────────────────────────────

type Rubric = { traits: EvalTrait[]; scoring: EvalProposal["scoring"]; instructions: string };
const CONTEXT = 3; // unchanged lines kept around each change, as git does

/** A rubric as the text file it would be: how it is scored, its description, then each trait
 * with what good and bad look like. */
function rubricText(r: Rubric): string {
  const lines = [`Scored by: ${SCORING[r.scoring]}`];
  if (r.instructions) lines.push("", r.instructions);
  for (const t of r.traits) lines.push("", `## ${t.name}`, `Good: ${t.good}`, `Bad: ${t.bad}`);
  return lines.join("\n");
}

interface NumberedLine { kind: "same" | "add" | "del"; text: string; old?: number; now?: number }

/** The line diff between the rubric in use and the proposed one, numbered on both sides. */
function rubricDiff(p: EvalProposal): { lines: NumberedLine[]; added: number; removed: number } {
  let old = 0, now = 0;
  const lines = diffLines(p.before ? rubricText(p.before) : "", rubricText(p)).map((l): NumberedLine => ({
    ...l, old: l.kind === "add" ? undefined : ++old, now: l.kind === "del" ? undefined : ++now,
  }));
  return { lines, added: lines.filter((l) => l.kind === "add").length, removed: lines.filter((l) => l.kind === "del").length };
}

/** The rubric change as a git-style diff of one file: removed lines in red, added lines in
 * green, a few unchanged lines around each change, and the rest folded away. */
function RubricDiff({ diff }: { diff: ReturnType<typeof rubricDiff> }) {
  const { lines } = diff;
  const near = lines.map((_, i) => lines.slice(Math.max(0, i - CONTEXT), i + CONTEXT + 1).some((l) => l.kind !== "same"));
  const cell = "select-none px-2 text-right tabular-nums text-muted-foreground";
  return <section aria-label="Rubric diff" className="min-w-0 overflow-hidden rounded border border-border font-[ui-monospace,SFMono-Regular,Menlo,monospace] text-[12px] leading-5">
    <div className="flex items-center gap-2 border-b border-border bg-surface/40 px-3 py-1.5">
      <span>rubric</span>
      <span className="tabular-nums text-emerald-700 dark:text-emerald-400">+{diff.added}</span>
      <span className="tabular-nums text-red-700 dark:text-red-400">-{diff.removed}</span>
    </div>
    {lines.map((l, i) => {
      if (!near[i]) {
        // One marker for each folded run of unchanged lines, saying where the next lines start.
        if (i > 0 && !near[i - 1]) return null;
        const next = lines.slice(i).find((x, k) => near[i + k]);
        return next ? <div key={i} className="bg-surface/40 px-3 text-muted-foreground">@@ -{next.old ?? ""} +{next.now ?? ""} @@</div> : null;
      }
      return <div key={i} data-kind={l.kind} className={cn("grid grid-cols-[40px_40px_16px_minmax(0,1fr)]", l.kind === "add" && "bg-emerald-500/10", l.kind === "del" && "bg-red-500/10")}>
        <span className={cell}>{l.old}</span>
        <span className={cell}>{l.now}</span>
        <span aria-hidden className={cn("select-none", l.kind === "add" ? "text-emerald-700 dark:text-emerald-400" : l.kind === "del" ? "text-red-700 dark:text-red-400" : "")}>{l.kind === "add" ? "+" : l.kind === "del" ? "-" : ""}</span>
        <span className="whitespace-pre-wrap break-words pr-3">{l.text}</span>
      </div>;
    })}
  </section>;
}

// ── Rubric quality ───────────────────────────────────────────────────────

type Quality = NonNullable<NonNullable<EvalProposal["checks"]>["rubric_quality"]>;

/** How the eval that grades this eval's rubrics scored the rubric in use and the proposed one:
 * an overall score, then each of its traits with the score under both and how far it moved.
 * Hovering a trait gives its reason for the proposed rubric's score. Each row opens that eval. */
function RubricQuality({ proposal: p, quality }: { proposal: EvalProposal; quality: Quality }) {
  const was = new Map((quality.before?.traits ?? []).map((t) => [t.trait, t]));
  const rows = [
    { name: "Overall", before: quality.before?.score, after: quality.after.score, why: "" },
    ...quality.after.traits.map((t) => ({ name: t.trait, before: was.get(t.trait)?.score, after: t.score, why: t.why })),
  ];
  const column = "w-px whitespace-nowrap pl-3 text-right align-top tabular-nums";
  const href = quality.eval ? `/reward-models/evals/${quality.eval.id}` : "";
  const moved = (before: number | undefined, after: number) => (before === undefined ? null : { id: "", before, after });
  return <section aria-label="Rubric quality" className="rounded border border-border px-3 py-2">
    <table className="w-full border-collapse text-[12px]">
      <thead>
        <tr className="text-left text-[11px] uppercase tracking-wide text-muted-foreground">
          <th scope="col" className="pb-2 font-medium">
            {quality.eval
              ? <Link href={`/reward-models/evals/${quality.eval.id}`} className="normal-case tracking-normal text-foreground underline-offset-2 hover:underline">
                {quality.eval.name}{quality.eval.version ? <span className="ml-1.5 text-muted-foreground">v{quality.eval.version}</span> : null}
              </Link>
              : "Trait"}
          </th>
          <th scope="col" className="whitespace-nowrap pb-2 pl-3 text-right font-normal normal-case tracking-normal"><span className={chipClass}>rubric</span></th>
          <th scope="col" className="whitespace-nowrap pb-2 pl-3 text-right font-normal normal-case tracking-normal"><span className={chipClass}>{changeBranch(p)}</span></th>
          <th scope="col" className={cn(column, "pb-2 font-medium text-foreground")}>Change</th>
        </tr>
      </thead>
      <tbody>
        {rows.map((r, i) => {
          const flip = moved(r.before, r.after);
          // With a grading eval, the whole row is a link to it: the name's link is stretched over the row.
          return <tr key={r.name} className={cn("border-t border-border", href && "relative hover:bg-surface/40")}>
            <th scope="row" title={r.why || undefined} className={cn("py-1.5 pr-3 text-left align-top font-normal", i === 0 && "font-medium")}>
              {href ? <Link href={href} className="text-foreground no-underline after:absolute after:inset-0">{r.name}</Link> : r.name}
            </th>
            <td className={cn(column, "py-1.5 text-muted-foreground")}>{r.before?.toFixed(2)}</td>
            <td className={cn(column, "py-1.5")}>{r.after.toFixed(2)}</td>
            <td className={cn(column, "py-1.5 font-medium", (!flip || unchanged(flip)) && "font-normal text-muted-foreground")}>{flip && delta(flip)}</td>
          </tr>;
        })}
      </tbody>
    </table>
  </section>;
}

// ── Evals ────────────────────────────────────────────────────────────────

/** How far a score moved, signed: "-0.88", "+0.03", "0.00". */
function delta(f: EvalFlip): string {
  const moved = f.after - f.before;
  return unchanged(f) ? "0.00" : `${moved > 0 ? "+" : "-"}${Math.abs(moved).toFixed(2)}`;
}

/** A score that reads the same to two decimals under both rubrics. */
const unchanged = (f: EvalFlip) => Math.abs(f.after - f.before) < 0.005;

function CallList({ proposal: p, hideSame }: { proposal: EvalProposal; hideSame: boolean }) {
  const [query, setQuery] = useState("");
  const [ascending, setAscending] = useState(false);
  const all = (p.checks?.calls?.calls ?? []).map((f) => ({ flip: f, call: p.calls[f.id] })).filter((r): r is { flip: EvalFlip; call: EvalChangeCall } => !!r.call)
    .map((r) => ({ ...r, name: r.call.name || r.call.asked || r.call.text.split("\n")[0] || r.call.files[0]?.name || "" }))
    .sort((a, b) => ((b.flip.after - b.flip.before) - (a.flip.after - a.flip.before)) * (ascending ? -1 : 1));
  if (all.length === 0) return null;
  const wanted = query.trim().toLowerCase();
  const rows = all.filter((r) => (!wanted || r.name.toLowerCase().includes(wanted)) && !(hideSame && unchanged(r.flip)));
  const column = "w-px whitespace-nowrap pl-3 text-right tabular-nums";
  return <table aria-label="Evals" className="w-full border-collapse text-[12px]">
    <thead>
      <tr className="text-left text-[11px] uppercase tracking-wide text-muted-foreground">
        <th scope="col" className="pb-2 font-medium">
          <span className="flex items-center gap-2">
            Evals
            <span className="relative flex items-center">
              <Search aria-hidden className="pointer-events-none absolute left-1.5 size-3" />
              <input type="search" value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Search" aria-label="Search evals"
                className="h-6 w-44 rounded border border-border bg-background pr-2 pl-6 text-[12px] font-normal normal-case tracking-normal text-foreground outline-none focus:border-foreground/40" />
            </span>
          </span>
        </th>
        <th scope="col" className="whitespace-nowrap pb-2 pl-3 text-right font-normal normal-case tracking-normal"><span className={chipClass}>rubric</span></th>
        <th scope="col" className="whitespace-nowrap pb-2 pl-3 text-right font-normal normal-case tracking-normal"><span className={chipClass}>{changeBranch(p)}</span></th>
        <th scope="col" aria-sort={ascending ? "ascending" : "descending"} className={cn(column, "pb-2 font-medium")}>
          <button type="button" onClick={() => setAscending(!ascending)} title={ascending ? "Largest drop first" : "Largest gain first"}
            className="inline-flex items-center gap-0.5 uppercase tracking-wide text-foreground hover:opacity-70">
            Change{ascending ? <ChevronUp aria-hidden className="size-3" /> : <ChevronDown aria-hidden className="size-3" />}
          </button>
        </th>
      </tr>
    </thead>
    <tbody>
      {rows.map(({ flip, call, name }) => (
        <tr key={call.id} title={flip.low ? `${flip.low.trait}: ${flip.low.why}` : undefined} className="border-t border-border">
          <td className="max-w-0 truncate py-1.5 pr-3">{name}</td>
          <td className={cn(column, "py-1.5 text-muted-foreground")}>{flip.before.toFixed(2)}</td>
          <td className={cn(column, "py-1.5")}>{flip.after.toFixed(2)}</td>
          <td className={cn(column, "py-1.5 font-medium", unchanged(flip) && "font-normal text-muted-foreground")}>{delta(flip)}</td>
        </tr>
      ))}
      {rows.length === 0 && <tr className="border-t border-border"><td colSpan={4} className="py-1.5 text-muted-foreground">No evals match</td></tr>}
    </tbody>
  </table>;
}
