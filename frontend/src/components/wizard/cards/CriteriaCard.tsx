"use client";

import { useEffect, useState } from "react";
import { Check, ListChecks, Plus, Sparkles, Trash2, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { errorMessage } from "@/components/reward-models/rm-text";
import { imEditDraft, imGet, type RubricQuestion } from "@/lib/intuition-api";
import { wzDiscover } from "@/lib/wizard-api";
import { cn } from "@/lib/utils";
import { CardShell, NeedsModel, SIGNAL_IDS, userCriteria, useWizard } from "../wizard-ui";

type Proposal = RubricQuestion & { insight?: string };
const MAX_CRITERIA = 10;

function slug(text: string, taken: Set<string>): string {
  let s = text.toLowerCase().replace(/[^a-z0-9]+/g, "_").replace(/^_+|_+$/g, "").slice(0, 40) || "criterion";
  while (taken.has(s)) s = `${s}_2`;
  return s;
}

function kindOf(q: RubricQuestion): string {
  if (q.type === "noul") return "yes / no";
  if (q.type === "score") return `scale, ${(q.criteria as string[]).length} levels`;
  return `pick one, ${Object.keys(q.criteria).length}`;
}

/** Co-create criteria: accept or dismiss proposals, edit wording, add your own, then save. */
export default function CriteriaCard({ proposals: initial = [] }: { proposals?: Proposal[] }) {
  const { modelId, send, refresh, version } = useWizard();
  const [criteria, setCriteria] = useState<RubricQuestion[] | null>(null);
  const [signals, setSignals] = useState<RubricQuestion[]>([]);
  const [proposals, setProposals] = useState<Proposal[]>(initial);
  const [draft, setDraft] = useState("");
  const [busy, setBusy] = useState<"" | "save" | "discover">("");
  const [dirty, setDirty] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    if (!modelId) return;
    imGet(modelId).then((d) => {
      const rubric = (d.draft ?? d.active)?.rubric ?? [];
      setCriteria(userCriteria(rubric));
      setSignals(rubric.filter((q) => SIGNAL_IDS.has(q.id)));
    }).catch((e) => setError(errorMessage(e)));
  }, [modelId, version]);

  if (!modelId) return <CardShell icon={ListChecks} title="Criteria"><NeedsModel /></CardShell>;
  const taken = new Set([...(criteria ?? []), ...signals].map((q) => q.id));
  const edit = (next: RubricQuestion[]) => { setCriteria(next); setDirty(true); };

  async function save() {
    if (!modelId || !criteria) return;
    setBusy("save"); setError("");
    try {
      await imEditDraft(modelId, { rubric: [...criteria, ...signals] });
      setDirty(false); refresh();
      send(`Saved ${criteria.length} criteria: ${criteria.map((q) => `“${q.prompt}”`).join("; ")}.`, "event");
    } catch (e) { setError(errorMessage(e)); } finally { setBusy(""); }
  }

  async function discover() {
    if (!modelId) return;
    setBusy("discover"); setError("");
    try {
      const found = await wzDiscover(modelId, { count: 3 });
      setProposals((p) => [...p, ...found.insights.map((i) => ({ ...i.question, insight: i.insight }))]);
    } catch (e) { setError(errorMessage(e)); } finally { setBusy(""); }
  }

  return (
    <CardShell
      icon={ListChecks}
      title="Criteria"
      subtitle="What the judge checks on every item. Ask about observable properties."
      actions={<Button size="xs" variant="ghost" disabled={!!busy} onClick={() => void discover()} title="Compare similar items you labeled differently"><Sparkles />{busy === "discover" ? "Finding…" : "Discover from my labels"}</Button>}
    >
      {proposals.length > 0 && (
        <div className="mb-3 space-y-1.5">
          <div className="text-[10.5px] font-medium tracking-wide text-muted-foreground uppercase">Suggested</div>
          {proposals.map((p, i) => (
            <div key={`${p.id}-${i}`} className="flex items-start gap-2 rounded-md border border-brand-500/25 bg-brand-500/5 px-2.5 py-2">
              <div className="min-w-0 flex-1">
                <p className="m-0 text-[12.5px]">{p.prompt}</p>
                {p.insight && <p className="m-0 mt-0.5 text-[11px] text-muted-foreground">Why: {p.insight}</p>}
                <p className="m-0 mt-0.5 font-mono text-[10.5px] text-muted-foreground">{kindOf(p)}</p>
              </div>
              <Button size="icon-xs" variant="ghost" aria-label={`Accept ${p.prompt}`} disabled={(criteria?.length ?? 0) >= MAX_CRITERIA} onClick={() => {
                const question: RubricQuestion = { id: taken.has(p.id) ? slug(p.prompt, taken) : p.id, type: p.type, prompt: p.prompt, criteria: p.criteria };
                edit([...(criteria ?? []), question]);
                setProposals((all) => all.filter((_, j) => j !== i));
              }}><Check /></Button>
              <Button size="icon-xs" variant="ghost" aria-label={`Dismiss ${p.prompt}`} onClick={() => setProposals((all) => all.filter((_, j) => j !== i))}><X /></Button>
            </div>
          ))}
        </div>
      )}
      {criteria === null ? <p className="m-0 text-[12px] text-muted-foreground">Loading…</p> : (
        <ol className="m-0 list-none space-y-1.5 p-0">
          {criteria.length === 0 && <li className="text-[12px] text-muted-foreground">No criteria yet — accept a suggestion or write one below.</li>}
          {criteria.map((q, i) => (
            <li key={q.id} className="flex items-center gap-2 rounded-md border border-border px-2.5 py-1.5">
              <span className="w-4 shrink-0 text-right font-mono text-[11px] text-muted-foreground">{i + 1}</span>
              <input aria-label={`Criterion ${i + 1}`} value={q.prompt} onChange={(e) => edit(criteria.map((c, j) => (j === i ? { ...c, prompt: e.target.value } : c)))} className="min-w-0 flex-1 bg-transparent text-[12.5px] outline-none" />
              <span className="shrink-0 font-mono text-[10.5px] text-muted-foreground">{kindOf(q)}</span>
              <Button size="icon-xs" variant="ghost" aria-label={`Remove criterion ${i + 1}`} onClick={() => edit(criteria.filter((_, j) => j !== i))}><Trash2 /></Button>
            </li>
          ))}
        </ol>
      )}
      <form className="mt-2 flex gap-1.5" onSubmit={(e) => {
        e.preventDefault();
        if (!draft.trim() || !criteria || criteria.length >= MAX_CRITERIA) return;
        edit([...criteria, { id: slug(draft, taken), type: "noul", prompt: draft.trim(), criteria: { true: "Yes", false: "No" } }]);
        setDraft("");
      }}>
        <input aria-label="New yes/no criterion" value={draft} onChange={(e) => setDraft(e.target.value)} placeholder="Add a yes/no criterion, e.g. “Does it answer the customer’s actual question?”" className="h-8 min-w-0 flex-1 rounded-md border border-border bg-background px-2.5 text-[12px] outline-none focus:border-foreground/40" />
        <Button type="submit" size="sm" variant="outline" disabled={!draft.trim()}><Plus />Add</Button>
      </form>
      <div className={cn("mt-3 flex items-center justify-between gap-2 text-[11.5px] text-muted-foreground")}>
        <span>{signals.length ? "Plus the zero-shot verdict and embedding probe, added automatically." : "The zero-shot verdict and embedding probe are added when you train."}</span>
        <Button size="sm" disabled={!dirty || busy === "save" || !criteria} onClick={() => void save()}>{busy === "save" ? "Saving…" : "Save criteria"}</Button>
      </div>
      {error && <p role="alert" className="m-0 mt-2 text-[11.5px] text-destructive">{error}</p>}
    </CardShell>
  );
}
