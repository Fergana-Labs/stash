"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { Wand2 } from "lucide-react";
import { useBreadcrumbs } from "@/components/BreadcrumbContext";
import { Button } from "@/components/ui/button";
import { EvalPageFrame } from "@/components/evals/eval-ui";
import { errorMessage } from "@/components/reward-models/rm-text";
import { wzCreate, wzSessions, type WizardSession } from "@/lib/wizard-api";

export default function WizardPage() {
  useBreadcrumbs([{ label: "Eval wizard" }], "evals");
  const router = useRouter();
  const [sessions, setSessions] = useState<WizardSession[] | null>(null);
  const [error, setError] = useState("");
  const [creating, setCreating] = useState(false);
  const load = useCallback(async () => { try { setSessions((await wzSessions()).sessions); } catch (e) { setError(errorMessage(e)); } }, []);
  useEffect(() => { void load(); }, [load]);

  async function start() {
    setCreating(true);
    try { router.push(`/reward-models/wizard/${(await wzCreate()).id}`); } catch (e) { setError(errorMessage(e)); setCreating(false); }
  }

  return <EvalPageFrame title="Eval wizard" description="Build an eval by talking it through: a handful of labels, no ML required." actions={<Button size="sm" disabled={creating} onClick={() => void start()}><Wand2 />New eval</Button>}>
    {error && <p role="alert" className="text-xs text-destructive">{error}</p>}
    {!sessions && !error && <p role="status" className="text-xs text-muted-foreground">Loading…</p>}
    {sessions && sessions.length === 0 && <div className="rounded-lg border border-dashed border-border p-8 text-center text-sm text-muted-foreground">No wizard sessions yet. <button className="underline" onClick={() => void start()}>Start one</button>.</div>}
    {sessions && sessions.length > 0 && <ul className="m-0 list-none divide-y divide-border rounded border border-border p-0">
      {sessions.map((s) => <li key={s.id}><Link href={`/reward-models/wizard/${s.id}`} className="flex items-center gap-3 px-3 py-2.5 text-xs hover:bg-surface/60">
        <Wand2 className="size-3.5 text-muted-foreground" /><span className="font-medium">{s.model_name ?? (s.title === "New model" ? "Untitled eval" : s.title)}</span>
        <span className="ml-auto text-muted-foreground">{new Date(s.updated_at).toLocaleString()}</span>
      </Link></li>)}
    </ul>}
  </EvalPageFrame>;
}
