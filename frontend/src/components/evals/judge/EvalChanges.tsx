"use client";

import Link from "next/link";
import { useState } from "react";
import { MessageSquare } from "lucide-react";
import { cn } from "@/lib/utils";
import { relativeTime } from "@/components/reward-models/rm-text";
import type { EvalChange, EvalChanges as Changes, EvalProposal } from "@/lib/evals-api";

const VERB: Record<string, string> = { add: "Add", tighten: "Tighten", fix: "Fix", point: "Point", remove: "Remove", request: "Change", write: "Rewrite", description: "Description", scoring: "Score by" };

/** What a proposal does, in a line: "Add Stripes, tighten Color". */
export function changeTitle(changes: EvalChange[]): string {
  const parts = changes.map((c, i) => {
    const verb = VERB[c.kind] ?? c.kind;
    return `${i === 0 ? verb : verb.toLowerCase()}${c.trait ? ` ${c.trait}` : ""}`;
  });
  return parts.slice(0, 3).join(", ") + (parts.length > 3 ? `, ${parts.length - 3} more` : "") || "Rubric change";
}

export const changePath = (evalId: string, number: number) => `/reward-models/evals/${evalId}/changes/${number}`;

/** An approved change is merged into the rubric; a rejected one is closed. */
export function changeState(p: EvalProposal): "open" | "merged" | "closed" {
  return p.status === "approved" ? "merged" : p.status === "rejected" ? "closed" : "open";
}

type Filter = "open" | "closed";

/** An eval's proposed rubric changes, listed the way pull requests are: the open ones, or the
 * ones already merged into the rubric or closed. Each opens on its own page. */
export default function EvalChanges({ evalId, changes }: { evalId: string; changes: Changes }) {
  const open = changes.proposals.filter((p) => p.status === "open");
  const closed = changes.proposals.filter((p) => p.status !== "open");
  const [filter, setFilter] = useState<Filter>(open.length === 0 && closed.length > 0 ? "closed" : "open");
  const shown = filter === "open" ? open : closed;
  const filters: { key: Filter; label: string; count: number }[] = [
    { key: "open", label: "Open", count: open.length },
    { key: "closed", label: "Closed", count: closed.length },
  ];
  return <section aria-label="Change requests" className="rounded border border-border text-[13px]">
    <div className="flex gap-1 border-b border-border px-2 py-1.5">
      {filters.map((f) => (
        <button key={f.key} type="button" aria-pressed={filter === f.key} onClick={() => setFilter(f.key)}
          className={cn("h-6 rounded-sm px-2 text-[12px]", filter === f.key ? "bg-surface font-medium text-foreground" : "text-muted-foreground hover:text-foreground")}>
          <span className="tabular-nums">{f.count}</span> {f.label}
        </button>
      ))}
    </div>
    {shown.length === 0
      ? <p className="m-0 px-3 py-2 text-[12px] text-muted-foreground">{filter === "open" ? "No open change requests" : "No closed change requests"}</p>
      : <ul className="m-0 list-none divide-y divide-border p-0">
        {shown.map((p) => <ChangeRow key={p.id} evalId={evalId} proposal={p} />)}
      </ul>}
  </section>;
}

function ChangeRow({ evalId, proposal: p }: { evalId: string; proposal: EvalProposal }) {
  const state = changeState(p);
  const outcome = state === "merged" ? `Merged${p.version ? ` as v${p.version}` : ""}` : state === "closed" ? "Closed" : p.stale ? "Out of date" : "";
  return <li>
    <Link href={changePath(evalId, p.number)} aria-label={`Change request ${p.number}: ${changeTitle(p.changes)}`}
      className="flex h-9 items-center gap-2.5 px-3 text-foreground no-underline hover:bg-surface/40">
      <span className="w-6 shrink-0 tabular-nums text-muted-foreground">#{p.number}</span>
      <span className="min-w-0 flex-1 truncate font-medium">{changeTitle(p.changes)}</span>
      {outcome && <span className="whitespace-nowrap text-[12px] text-muted-foreground">{outcome}</span>}
      {p.comments.length > 0 && <span className="flex items-center gap-1 whitespace-nowrap text-[12px] tabular-nums text-muted-foreground" title="Comments">
        <MessageSquare aria-hidden className="size-3.5" />{p.comments.length}
      </span>}
      <span className="whitespace-nowrap text-[12px] text-muted-foreground">{p.opened_by ?? "Unknown"}</span>
      <time className="w-14 whitespace-nowrap text-right text-[12px] text-muted-foreground" dateTime={p.created_at}>{relativeTime(p.created_at)}</time>
    </Link>
  </li>;
}
