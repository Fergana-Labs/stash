"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { useBreadcrumbs } from "@/components/BreadcrumbContext";
import { Button } from "@/components/ui/button";
import { EvalPageFrame } from "@/components/evals/eval-ui";
import { errorMessage } from "@/components/reward-models/rm-text";
import { wizardSessionName, wzCreate, wzSessions, type WizardSession } from "@/lib/wizard-api";

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

  return <EvalPageFrame title="Eval wizard" description="Build an eval by talking it through: a handful of labels, no ML required." actions={<Button size="sm" disabled={creating} onClick={() => void start()}>New eval</Button>}>
    {error && <p role="alert" className="text-xs text-destructive">{error}</p>}
    {!sessions && !error && <p role="status" className="text-xs text-muted-foreground">Loading…</p>}
    {sessions && sessions.length === 0 && <div className="rounded border border-dashed border-border p-6 text-center text-xs text-muted-foreground">No wizard sessions yet. <button className="underline" onClick={() => void start()}>Start one</button>.</div>}
    {sessions && sessions.length > 0 && <div className="overflow-x-auto rounded border border-border">
      <table aria-label="Eval wizard sessions" className="w-full min-w-[480px] text-left text-xs">
        <thead className="border-b border-border bg-surface text-muted-foreground"><tr className="h-8 [&>th]:px-3 [&>th]:font-medium"><th>Eval</th><th className="w-44 text-right">Last updated</th></tr></thead>
        <tbody>{sessions.map((s) => <tr key={s.id} className="border-b border-border last:border-b-0 hover:bg-surface/60">
          <td className="px-3"><div className="flex items-center gap-2"><Link href={s.status === "saved" && s.model_id ? `/reward-models/evals/${s.model_id}` : `/reward-models/wizard/${s.id}`} className="py-2.5 font-medium hover:underline">{wizardSessionName(s)}</Link>{s.status !== "saved" && <span className="ml-auto shrink-0 rounded border border-border px-1.5 py-0.5 text-[10px] text-muted-foreground">Draft</span>}</div></td>
          <td className="px-3 text-right tabular-nums whitespace-nowrap text-muted-foreground"><time dateTime={s.updated_at}>{new Date(s.updated_at).toLocaleString(undefined, { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" })}</time></td>
        </tr>)}</tbody>
      </table>
    </div>}
  </EvalPageFrame>;
}
