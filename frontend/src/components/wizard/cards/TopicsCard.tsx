"use client";

import { useCallback, useEffect, useState } from "react";
import { Layers, RefreshCw } from "lucide-react";
import { Button } from "@/components/ui/button";
import { errorMessage } from "@/components/reward-models/rm-text";
import { wzRefreshTopics, wzTopics, type Topics } from "@/lib/wizard-api";
import { cn } from "@/lib/utils";
import { CardShell, NeedsModel, pct, useWizard } from "../wizard-ui";
import InboxCard from "./InboxCard";

/** Traffic and examples clustered by subject, so review goes where the judge gets overturned. */
export default function TopicsCard() {
  const { modelId, version } = useWizard();
  const [data, setData] = useState<Topics | null>(null);
  const [busy, setBusy] = useState(false);
  const [focus, setFocus] = useState<string | null>(null);
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    if (!modelId) return;
    try { setData(await wzTopics(modelId)); } catch (e) { setError(errorMessage(e)); }
  }, [modelId]);
  useEffect(() => { void load(); }, [load, version]);

  if (!modelId) return <CardShell icon={Layers} title="Topics"><NeedsModel /></CardShell>;

  async function recompute() {
    if (!modelId) return;
    setBusy(true); setError("");
    try { setData(await wzRefreshTopics(modelId)); } catch (e) { setError(errorMessage(e)); } finally { setBusy(false); }
  }

  const topics = [...(data?.topics ?? [])].sort((a, b) => (b.overturn_rate ?? -1) - (a.overturn_rate ?? -1) || b.unreviewed - a.unreviewed);

  return (
    <>
      <CardShell
        icon={Layers}
        title="Topics"
        subtitle={data?.computed_at ? `Grouped ${new Date(data.computed_at).toLocaleString()} · weakest first` : "Not grouped yet"}
        actions={<Button size="xs" variant="ghost" disabled={busy} onClick={() => void recompute()}><RefreshCw className={cn(busy && "animate-spin")} />{busy ? "Grouping…" : data?.computed_at ? "Regroup" : "Group"}</Button>}
      >
        {error && <p role="alert" className="m-0 mb-2 text-[11.5px] text-destructive">{error}</p>}
        {data && topics.length === 0 && <p className="m-0 text-[12px] text-muted-foreground">Group examples and recent traffic by subject to see where the judge is weakest and route review there.</p>}
        {topics.length > 0 && (
          <table className="w-full text-[12px]">
            <thead><tr className="text-left text-[10.5px] tracking-wide text-muted-foreground uppercase"><th className="pb-1 font-medium">Topic</th><th className="pb-1 text-right font-medium">Traffic</th><th className="pb-1 text-right font-medium">Overturned</th><th className="pb-1 text-right font-medium">Held-out</th><th /></tr></thead>
            <tbody>
              {topics.map((t) => (
                <tr key={t.id} className="border-t border-border align-top">
                  <td className="py-1.5 pr-2"><div className="font-medium">{t.name}</div><div className="text-[11px] text-muted-foreground">{t.description}</div><div className="mt-0.5 font-mono text-[10.5px] text-muted-foreground">{Object.entries(t.examples).map(([l, n]) => `${n} ${l}`).join(" · ") || "no examples"}</div></td>
                  <td className="py-1.5 text-right tabular-nums">{t.served}{t.unreviewed ? <div className="text-[10.5px] text-muted-foreground">{t.unreviewed} open</div> : null}</td>
                  <td className={cn("py-1.5 text-right tabular-nums", (t.overturn_rate ?? 0) >= 0.25 && "font-semibold text-red-600 dark:text-red-400")}>{t.reviewed ? `${t.overturned}/${t.reviewed}` : "—"}</td>
                  <td className="py-1.5 text-right tabular-nums">{t.held_out.n ? pct(t.held_out.accuracy) : "—"}{t.held_out.n ? <div className="text-[10.5px] text-muted-foreground">on {t.held_out.n}</div> : null}</td>
                  <td className="py-1.5 pl-2 text-right">{t.unreviewed > 0 && <Button size="xs" variant={focus === t.id ? "default" : "outline"} onClick={() => setFocus(focus === t.id ? null : t.id)}>Review</Button>}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </CardShell>
      {focus && <InboxCard key={focus} topic={focus} />}
    </>
  );
}
