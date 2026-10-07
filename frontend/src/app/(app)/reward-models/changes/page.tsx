"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { Suspense, useCallback, useState } from "react";
import { useBreadcrumbs } from "@/components/BreadcrumbContext";
import { Button } from "@/components/ui/button";
import { EmptyState, RmPage } from "@/components/reward-models/rm-ui";
import { relativeTime } from "@/components/reward-models/rm-text";
import { ErrorNotice, RecordBadge, RecordPanel, useWorkbenchLoad } from "@/components/workbench/workbench-ui";
import { wbGetChange, wbListChanges } from "@/lib/workbench-api";

import ChangeEditor from "@/components/workbench/ChangeEditor";

export default function ChangesPage() { return <Suspense><Changes /></Suspense>; }

function Changes() {
  useBreadcrumbs([{ label: "Changes" }], "workbench-changes");
  const searchParams = useSearchParams();
  const { data, loading, error, reload } = useWorkbenchLoad(wbListChanges, 5000);
  const [selected, setSelected] = useState<string | null>(searchParams.get("change"));
  const [filter, setFilter] = useState("all");
  const visible = data?.filter((change) => filter === "all" || change.kind === filter) ?? [];
  return <RmPage title="Changes" description="Inspect exact proposed instructions, check results, and release history. Grader changes and agent instructions are released independently.">
    <ErrorNotice error={error} onRetry={() => void reload()} />
    <div className="mb-4 flex gap-2">{[["all", "All changes"], ["grader", "Grader changes"], ["instruction", "Agent instructions"]].map(([value, label]) => <Button key={value} size="sm" variant={filter === value ? "secondary" : "ghost"} aria-pressed={filter === value} onClick={() => setFilter(value)}>{label}</Button>)}</div>
    {loading && <p className="text-[13px] text-muted-foreground">Loading changes…</p>}
    {!loading && !error && visible.length === 0 && <EmptyState title="No proposed changes">Accept a correction in <Link href="/reward-models/review" className="underline">Review</Link>, or propose a configuration in <Link href="/reward-models/graders" className="underline">Graders</Link>.</EmptyState>}
    <div className="space-y-3">{visible.map((change) => <RecordPanel key={change.id} title={<button type="button" className="cursor-pointer text-left hover:underline" onClick={() => setSelected(selected === change.id ? null : change.id)}>{change.title}</button>} actions={<RecordBadge value={change.status} />}>
      <div className="flex flex-wrap gap-3 text-[12px] text-muted-foreground"><span>{change.kind === "grader" ? "Grader configuration" : "Agent instruction"}</span><span>Created {relativeTime(change.created_at)}</span>{change.released_at && <span>Released {relativeTime(change.released_at)}</span>}</div>
      <Button variant="link" size="sm" className="mt-2 px-0" onClick={() => setSelected(selected === change.id ? null : change.id)}>{selected === change.id ? "Close change" : "Inspect change, checks, and delivery"}</Button>
      {selected === change.id && <ChangeDetail id={change.id} onChanged={reload} />}
    </RecordPanel>)}</div>
  </RmPage>;
}

function ChangeDetail({ id, onChanged }: { id: string; onChanged: () => Promise<void> }) {
  const loader = useCallback(() => wbGetChange(id), [id]);
  const { data, error, loading, reload } = useWorkbenchLoad(loader, 5000);
  return <div className="mt-3 border-t border-border pt-4"><ErrorNotice error={error} onRetry={() => void reload()} />{loading && <p className="text-[12px] text-muted-foreground">Loading change…</p>}{data && <ChangeEditor key={`${data.id}-${data.status}-${data.released_at}`} change={data} onChanged={async () => { await reload(); await onChanged(); }} />}</div>;
}
