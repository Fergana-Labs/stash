"use client";

import { useCallback, useEffect, useState } from "react";
import { ClipboardList, Pencil } from "lucide-react";
import { Button } from "@/components/ui/button";
import { errorMessage } from "@/components/reward-models/rm-text";
import { wzBrief, wzSaveBrief, type Brief, type BriefLabel, type BriefState } from "@/lib/wizard-api";
import { cn } from "@/lib/utils";
import { CardShell, NeedsModel, useWizard } from "../wizard-ui";

const TEXT_FIELDS = ["decision", "input", "costly_mistake", "context", "success"] as const;
const LIST_FIELDS = ["must_never", "edge_cases", "reviewers"] as const;
const TITLES: Record<keyof Brief, string> = {
  decision: "Decision", input: "Input", labels: "Labels and boundaries", costly_mistake: "Worse mistake",
  must_never: "Must never get wrong", edge_cases: "Edge cases", context: "Context", success: "Good enough means", reviewers: "Other reviewers",
};
const ORDER: (keyof Brief)[] = ["decision", "input", "labels", "costly_mistake", "must_never", "edge_cases", "context", "success", "reviewers"];
const inputClass = "w-full resize-y rounded-md border border-border bg-background px-2.5 py-1.5 text-[12.5px] outline-none focus:border-foreground/40";

const lines = (v: string) => v.split("\n").map((l) => l.trim()).filter(Boolean);
const labelsToText = (labels: BriefLabel[] = []) => labels.map((l) => `${l.id}: ${l.means}${l.not ? ` | not: ${l.not}` : ""}`).join("\n");
function textToLabels(text: string): BriefLabel[] {
  return lines(text).map((line) => {
    const [head, ...rest] = line.split(":");
    const [means, not] = rest.join(":").split("| not:");
    return { id: head.trim(), means: (means ?? "").trim(), ...(not?.trim() ? { not: not.trim() } : {}) };
  });
}

/** What the eval is held to: the decision, label boundaries, the costly mistake, the must-never cases. */
export default function BriefCard() {
  const { modelId, send, refresh, version } = useWizard();
  const [state, setState] = useState<BriefState | null>(null);
  const [draft, setDraft] = useState<Record<string, string> | null>(null);
  const [error, setError] = useState("");
  const [saving, setSaving] = useState(false);

  const load = useCallback(async () => {
    if (!modelId) return;
    try { setState(await wzBrief(modelId)); } catch (e) { setError(errorMessage(e)); }
  }, [modelId]);
  useEffect(() => { void load(); }, [load, version]);

  if (!modelId) return <CardShell icon={ClipboardList} title="Eval brief"><NeedsModel /></CardShell>;

  function edit() {
    const b = state?.brief ?? {};
    const d: Record<string, string> = { labels: labelsToText(b.labels) };
    for (const k of TEXT_FIELDS) d[k] = b[k] ?? "";
    for (const k of LIST_FIELDS) d[k] = (b[k] ?? []).join("\n");
    setDraft(d);
  }

  async function save() {
    if (!modelId || !draft) return;
    setSaving(true); setError("");
    const changes: Record<string, unknown> = { labels: draft.labels.trim() ? textToLabels(draft.labels) : null };
    for (const k of TEXT_FIELDS) changes[k] = draft[k].trim() || null;
    for (const k of LIST_FIELDS) changes[k] = lines(draft[k]).length ? lines(draft[k]) : null;
    try {
      setState(await wzSaveBrief(modelId, changes));
      setDraft(null); refresh();
      send("Edited the eval brief.", "event");
    } catch (e) { setError(errorMessage(e)); } finally { setSaving(false); }
  }

  const b = state?.brief ?? {};
  const missing = new Set(state?.missing ?? []);
  const required = ORDER.filter((k) => !state?.optional_missing.includes(k) || b[k]);
  const filled = state ? ORDER.length - state.missing.length - state.optional_missing.length : 0;

  return (
    <CardShell
      icon={ClipboardList}
      title="Eval brief"
      subtitle={state ? (state.complete ? `Complete · ${filled} of ${ORDER.length} filled` : `Missing: ${state.missing.map((k) => TITLES[k].toLowerCase()).join(", ")}`) : "Loading…"}
      actions={draft ? undefined : <Button size="xs" variant="ghost" onClick={edit}><Pencil />Edit</Button>}
    >
      {error && <p role="alert" className="m-0 mb-2 text-[11.5px] text-destructive">{error}</p>}
      {draft ? (
        <div className="space-y-2.5">
          {ORDER.map((k) => (
            <label key={k} className="block">
              <span className="mb-0.5 block text-[11px] font-medium text-muted-foreground">{TITLES[k]}{k === "labels" ? " — one per line: id: what it means | not: the nearest thing it isn't" : LIST_FIELDS.includes(k as never) ? " — one per line" : ""}</span>
              <textarea aria-label={TITLES[k]} rows={k === "labels" || LIST_FIELDS.includes(k as never) ? 3 : 2} className={inputClass} value={draft[k]} onChange={(e) => setDraft({ ...draft, [k]: e.target.value })} />
            </label>
          ))}
          <div className="flex gap-2"><Button size="sm" disabled={saving} onClick={() => void save()}>{saving ? "Saving…" : "Save brief"}</Button><Button size="sm" variant="ghost" onClick={() => setDraft(null)}>Cancel</Button></div>
        </div>
      ) : state && (
        <dl className="m-0 grid gap-x-4 gap-y-2 text-[12.5px] sm:grid-cols-[9.5rem_1fr]">
          {(state.complete ? required : ORDER).map((k) => {
            const v = b[k];
            const shown = k === "labels"
              ? (v as BriefLabel[] | undefined)?.map((l) => <div key={l.id}><span className="font-mono text-[11.5px]">{l.id}</span> — {l.means}{l.not && <span className="text-muted-foreground"> (not: {l.not})</span>}</div>)
              : Array.isArray(v) ? <ul className="m-0 list-disc pl-4">{(v as string[]).map((x) => <li key={x}>{x}</li>)}</ul> : v;
            return (
              <div key={k} className="contents">
                <dt className={cn("text-[11.5px] font-medium", missing.has(k) ? "text-amber-700 dark:text-amber-400" : "text-muted-foreground")}>{TITLES[k]}</dt>
                <dd className="m-0 min-w-0">{v && (!Array.isArray(v) || v.length) ? shown : <span className="text-muted-foreground italic">{missing.has(k) ? "Needed for a good eval" : "Optional"}</span>}</dd>
              </div>
            );
          })}
        </dl>
      )}
    </CardShell>
  );
}
