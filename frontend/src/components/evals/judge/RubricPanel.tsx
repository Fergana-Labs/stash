"use client";

import { useState } from "react";
import { Loader2, Plus, X } from "lucide-react";
import { cn } from "@/lib/utils";
import { errorMessage, relativeTime } from "@/components/reward-models/rm-text";
import { EVAL_BUILDING, type Eval, type EvalMetrics, type EvalRubricVersion, type EvalTrait } from "@/lib/evals-api";

const STAGE: Record<string, string> = {
  queued: "Updating", starting: "Updating", traits: "Writing", checking: "Checking", revising: "Revising",
};
const SOURCE: Record<EvalRubricVersion["source"], string> = { written: "Written", revised: "Revised", edited: "Edited" };
const VERB: Record<string, string> = { add: "Added", tighten: "Tightened", fix: "Fixed", point: "Pointed", remove: "Removed", request: "Changed", write: "Wrote", description: "Description", scoring: "Now scored by" };
const buttonClass = "h-6 rounded border border-border px-2 text-[12px] hover:bg-surface disabled:opacity-50";

/** The eval's rubric, the living artifact: what the judge checks now, how well it agrees with
 * the person's labels, every version it has had and why, and the endpoint that scores with it. */
export default function RubricPanel({ data, versions, onSave, onRewrite }: {
  data: Eval;
  versions: EvalRubricVersion[];
  onSave: (traits: EvalTrait[], base: number) => Promise<void>;
  onRewrite: () => Promise<void>;
}) {
  const [editing, setEditing] = useState(false);
  const current = versions[0];
  const building = !!data.build && EVAL_BUILDING.includes(data.build.stage);
  const failed = data.build?.stage === "failed";
  return (
    <aside aria-label="Rubric" className="space-y-3 text-[13px]">
      <header className="flex items-center gap-2">
        <h2 className="m-0 text-[13px] font-semibold">Rubric{current ? ` v${current.number}` : ""}</h2>
        {building && data.build && (
          <span role="status" className="flex items-center gap-1 text-[12px] text-muted-foreground">
            <Loader2 className="size-3 animate-spin" />{STAGE[data.build.stage]}
            {data.build.stage === "checking" && data.build.total ? ` ${data.build.done ?? 0}/${data.build.total}` : ""}
          </span>
        )}
        {current && !editing && (
          <span className="ml-auto flex gap-1.5">
            <button type="button" className={buttonClass} onClick={() => setEditing(true)}>Edit</button>
            <RewriteButton disabled={building} onRewrite={onRewrite} />
          </span>
        )}
      </header>
      {failed && <p role="alert" className="text-[12px] text-destructive">Update failed: {data.build?.error || "unknown error"}</p>}
      {current && <Agreement metrics={current.metrics} scoring={current.scoring} />}
      {data.instructions && <p className="text-[12px] text-muted-foreground">{data.instructions}</p>}
      {current && (editing
        ? <RubricEditor traits={current.traits} onCancel={() => setEditing(false)} onSave={async (traits) => { await onSave(traits, current.number); setEditing(false); }} />
        : <Traits traits={current.traits} />)}
      {versions.length > 0 && <History versions={versions} />}
      {data.ready && <Endpoint data={data} />}
    </aside>
  );
}

function RewriteButton({ disabled, onRewrite }: { disabled: boolean; onRewrite: () => Promise<void> }) {
  const [busy, setBusy] = useState(false);
  return <button type="button" className={buttonClass} disabled={disabled || busy}
    onClick={() => { setBusy(true); void onRewrite().finally(() => setBusy(false)); }}>Rewrite</button>;
}

function Agreement({ metrics, scoring }: { metrics: EvalMetrics | null; scoring: EvalRubricVersion["scoring"] }) {
  if (!metrics || (!metrics.fit?.n && !metrics.manipulation)) return null;
  const tried = metrics.manipulation;
  return <dl className="m-0 flex flex-wrap gap-x-4 gap-y-0.5 text-[12px]">
    <div className="flex gap-1.5"><dt className="text-muted-foreground">Scored by</dt><dd className="m-0">{scoring === "lowest" ? "Lowest trait" : "Average"}</dd></div>
    {metrics.fit?.n > 0 && <div className="flex gap-1.5"><dt className="text-muted-foreground">Learned from</dt><dd className="m-0 tabular-nums">{metrics.fit.right}/{metrics.fit.n}</dd></div>}
    {metrics.check?.n > 0 && <div className="flex gap-1.5"><dt className="text-muted-foreground">Held out</dt><dd className="m-0 tabular-nums">{metrics.check.right}/{metrics.check.n}</dd></div>}
    {tried && <div className="flex gap-1.5" title={tried.resisted < tried.n ? `Scored ${tried.worst.score.toFixed(2)} with: ${tried.worst.claim}` : undefined}>
      <dt className="text-muted-foreground">Manipulation resisted</dt>
      <dd className={cn("m-0 tabular-nums", tried.resisted < tried.n && "text-destructive")}>{tried.resisted}/{tried.n}</dd>
    </div>}
  </dl>;
}

/** Trait names first; each opens to what good and bad look like and the evidence behind it. */
function Traits({ traits }: { traits: EvalTrait[] }) {
  return <ol className="m-0 list-none divide-y divide-border rounded border border-border p-0">
    {traits.map((t) => (
      <li key={t.name}>
        <details className="group">
          <summary className="flex h-8 cursor-pointer list-none items-center gap-2 px-2.5 [&::-webkit-details-marker]:hidden">
            <span className="min-w-0 flex-1 truncate font-medium">{t.name}</span>
            {t.by === "person" && <span className="text-[11px] text-blue-600 dark:text-blue-400">Yours</span>}
          </summary>
          <div className="space-y-0.5 px-2.5 pb-2 text-[12px]">
            <p className="m-0"><span className="text-muted-foreground">Good</span> {t.good}</p>
            <p className="m-0"><span className="text-muted-foreground">Bad</span> {t.bad}</p>
            {t.basis && <p className="m-0 pt-0.5 text-[11px] text-muted-foreground">{t.basis}</p>}
          </div>
        </details>
      </li>
    ))}
  </ol>;
}

const fieldClass = "w-full rounded-sm border border-border bg-background px-2 py-1 text-[12px] outline-none focus:border-foreground/40";

function RubricEditor({ traits: initial, onSave, onCancel }: { traits: EvalTrait[]; onSave: (traits: EvalTrait[]) => Promise<void>; onCancel: () => void }) {
  const [traits, setTraits] = useState(initial);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const set = (i: number, field: keyof EvalTrait, value: string) => setTraits(traits.map((t, j) => (j === i ? { ...t, [field]: value } : t)));
  const names = traits.map((t) => t.name.trim().toLowerCase());
  const invalid = traits.length === 0 || names.some((n) => !n) || new Set(names).size < names.length;
  async function save() {
    setSaving(true); setError("");
    try { await onSave(traits.map((t) => ({ ...t, name: t.name.trim() }))); } catch (e) { setError(errorMessage(e)); setSaving(false); }
  }
  return <div className="space-y-2">
    {traits.map((t, i) => (
      <fieldset key={i} className="m-0 space-y-1 rounded border border-border p-2">
        <div className="flex items-center gap-1.5">
          <input aria-label="Trait name" value={t.name} maxLength={60} onChange={(e) => set(i, "name", e.target.value)} className={cn(fieldClass, "font-medium")} />
          <button type="button" aria-label={`Remove ${t.name || "trait"}`} onClick={() => setTraits(traits.filter((_, j) => j !== i))} className="text-muted-foreground hover:text-destructive"><X className="size-3.5" /></button>
        </div>
        <textarea aria-label="Good" placeholder="Good" rows={2} maxLength={400} value={t.good} onChange={(e) => set(i, "good", e.target.value)} className={cn(fieldClass, "resize-none")} />
        <textarea aria-label="Bad" placeholder="Bad" rows={2} maxLength={400} value={t.bad} onChange={(e) => set(i, "bad", e.target.value)} className={cn(fieldClass, "resize-none")} />
      </fieldset>
    ))}
    {traits.length < 10 && <button type="button" className={cn(buttonClass, "flex items-center gap-1")} onClick={() => setTraits([...traits, { name: "", good: "", bad: "" }])}><Plus className="size-3" />Add trait</button>}
    {error && <p role="alert" className="text-[12px] text-destructive">{error}</p>}
    <div className="flex gap-1.5">
      <button type="button" disabled={saving || invalid} onClick={() => void save()} className="h-6 rounded bg-foreground px-2 text-[12px] text-background disabled:opacity-50">{saving ? "Saving" : "Save"}</button>
      <button type="button" disabled={saving} onClick={onCancel} className={buttonClass}>Cancel</button>
    </div>
  </div>;
}

function History({ versions }: { versions: EvalRubricVersion[] }) {
  return <details className="text-[12px]">
    <summary className="cursor-pointer text-muted-foreground">History</summary>
    <ol className="m-0 mt-1.5 list-none space-y-2 p-0">
      {versions.map((v) => (
        <li key={v.id}>
          <div className="flex items-baseline gap-2">
            <span className="font-medium">v{v.number}</span>
            <span>{SOURCE[v.source]}</span>
            {v.metrics && v.metrics.fit.n > 0 && <span className="tabular-nums text-muted-foreground">{v.metrics.fit.right}/{v.metrics.fit.n}{v.metrics.check.n > 0 ? `, held out ${v.metrics.check.right}/${v.metrics.check.n}` : ""}</span>}
            <time className="ml-auto text-muted-foreground" dateTime={v.created_at}>{relativeTime(v.created_at)}</time>
          </div>
          {v.changes.length > 0 && (
            <ul className="m-0 list-none p-0">
              {v.changes.map((c, i) => <li key={i}><span>{VERB[c.kind] ?? c.kind}{c.trait ? ` ${c.trait}` : ""}</span>{c.why && <span className="text-muted-foreground">: {c.why}</span>}</li>)}
            </ul>
          )}
        </li>
      ))}
    </ol>
  </details>;
}

function Endpoint({ data }: { data: Eval }) {
  const origin = typeof window === "undefined" ? "https://api.joinstash.ai" : window.location.origin;
  const url = `${origin}${data.endpoint}`;
  const json = `curl ${url} \\
  -H "Authorization: Bearer $STASH_API_KEY" -H "Content-Type: application/json" \\
  -d '{"trace": [{"role": "user", "content": "what the agent was asked"}],
       "output": {"text": "what it produced", "images": ["<base64 PNG/JPEG, optional>"]},
       "caller": "my-agent"}'`;
  const multipart = `curl ${url} -H "Authorization: Bearer $STASH_API_KEY" \\
  -F trace='[{"role": "user", "content": "what the agent was asked"}]' \\
  -F text="what it produced" -F files=@output.png -F caller=my-agent`;
  return <details className="text-[12px]">
    <summary className="cursor-pointer text-muted-foreground">Endpoint</summary>
    <pre className="mt-1.5 overflow-x-auto rounded-sm bg-surface/60 p-2 text-[11px]">{json}</pre>
    <pre className="mt-1.5 overflow-x-auto rounded-sm bg-surface/60 p-2 text-[11px]">{multipart}</pre>
  </details>;
}
