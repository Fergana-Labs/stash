"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import { Plus } from "lucide-react";
import { useBreadcrumbs } from "@/components/BreadcrumbContext";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { EvalPageFrame, evalInputClass } from "@/components/evals/eval-ui";
import { EvalsViewToggle, GateBadge } from "@/components/test-sets/test-set-ui";
import { errorMessage, relativeTime } from "@/components/reward-models/rm-text";
import { pct, setHref, tsCreate, tsList, type TestSetSummary } from "@/lib/test-sets-api";

export default function TestSetsPage() {
  useBreadcrumbs([{ label: "Evals", href: "/reward-models/evals" }, { label: "Test sets" }], "test-sets");
  const router = useRouter();
  const [sets, setSets] = useState<TestSetSummary[] | null>(null);
  const [error, setError] = useState("");
  const [creating, setCreating] = useState(false);
  const load = useCallback(async () => { try { setSets((await tsList()).test_sets); setError(""); } catch (e) { setError(errorMessage(e)); } }, []);
  useEffect(() => { void load(); }, [load]);

  return <EvalPageFrame title="Evals" description="Test sets are inputs your agent must keep getting right. Run them on every change; a run fails when a case that used to pass breaks."
    actions={<Button size="sm" onClick={() => setCreating(true)}><Plus />New test set</Button>}>
    <EvalsViewToggle view="test-sets" />
    {error && <p role="alert" className="mb-2 text-xs text-destructive">{error} <button className="underline" onClick={() => void load()}>Retry</button></p>}
    <div className="overflow-x-auto rounded border border-border"><table aria-label="Test sets" className="w-full min-w-[640px] text-left text-xs">
      <thead className="border-b border-border bg-surface/60 text-muted-foreground"><tr className="h-8 [&>th]:px-3 [&>th]:font-medium"><th>Test set</th><th className="text-right">Cases</th><th>Last run</th><th className="text-right">Passed</th><th>Gate</th></tr></thead>
      <tbody>
        {sets?.map((s) => {
          const run = s.last_run;
          const broke = run?.summary?.broke.length ?? 0;
          return <tr key={s.id} className="h-11 cursor-pointer border-b border-border hover:bg-surface/60 [&>td]:px-3" onClick={(event) => {
            if ((event.target as HTMLElement).closest("a")) return;
            router.push(setHref(s.id));
          }}>
            <td><Link href={setHref(s.id)} className="block py-2 font-medium">{s.name}</Link>{s.description && <div className="-mt-1.5 pb-2 text-muted-foreground line-clamp-1">{s.description}</div>}</td>
            <td className="text-right tabular-nums">{s.case_count}</td>
            <td className="text-muted-foreground">{run ? <>{run.label || "Unlabeled"}, {relativeTime(run.created_at)}</> : "Never run"}</td>
            <td className="text-right tabular-nums">{run?.status === "scoring" ? <span className="text-muted-foreground">Scoring…</span>
              : run?.summary ? <>{pct(run.summary.pass_rate)}{broke > 0 && <span className="ml-2 text-destructive">{broke} broke</span>}</> : "—"}</td>
            <td>{run?.summary && run.summary.baseline ? <GateBadge gate={run.summary.gate} /> : <span className="text-muted-foreground">—</span>}</td>
          </tr>;
        })}
        {!sets && !error && <tr><td colSpan={5} className="px-3 py-6"><span role="status" className="text-muted-foreground">Loading test sets…</span></td></tr>}
        {sets && !sets.length && <tr><td colSpan={5} className="px-3 py-8 text-muted-foreground">No test sets yet. Create one, then add cases from production traces or a JSONL file.</td></tr>}
      </tbody>
    </table></div>
    <CreateTestSetDialog open={creating} onOpenChange={setCreating} onCreated={(id) => router.push(setHref(id))} />
  </EvalPageFrame>;
}

function CreateTestSetDialog({ open, onOpenChange, onCreated }: { open: boolean; onOpenChange: (open: boolean) => void; onCreated: (id: string) => void }) {
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  async function create() {
    setBusy(true); setError("");
    try { onCreated((await tsCreate({ name: name.trim(), description: description.trim() })).id); }
    catch (e) { setError(errorMessage(e)); } finally { setBusy(false); }
  }
  return <Dialog open={open} onOpenChange={onOpenChange}><DialogContent className="max-w-md">
    <DialogHeader><DialogTitle>New test set</DialogTitle><DialogDescription>Cases are scored against their expected answer. You can add evals as scorers later.</DialogDescription></DialogHeader>
    <form id="new-test-set" className="grid gap-3 text-xs" onSubmit={(e) => { e.preventDefault(); if (name.trim() && !busy) void create(); }}>
      <label className="grid gap-1"><span className="font-medium">Name</span><input autoFocus className={evalInputClass} value={name} maxLength={120} onChange={(e) => setName(e.target.value)} placeholder="Support regressions" /></label>
      <label className="grid gap-1"><span className="font-medium">Description <span className="font-normal text-muted-foreground">(optional)</span></span><textarea className={evalInputClass} rows={3} value={description} maxLength={4000} onChange={(e) => setDescription(e.target.value)} placeholder="What these cases protect" /></label>
      {error && <p role="alert" className="text-destructive">{error}</p>}
    </form>
    <DialogFooter><Button size="sm" variant="outline" onClick={() => onOpenChange(false)}>Cancel</Button><Button size="sm" type="submit" form="new-test-set" disabled={!name.trim() || busy}>{busy ? "Creating…" : "Create"}</Button></DialogFooter>
  </DialogContent></Dialog>;
}
