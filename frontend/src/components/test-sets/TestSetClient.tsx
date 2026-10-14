"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";
import { ChevronDown, ChevronRight, Plus, Trash2, Upload, X } from "lucide-react";
import { toast } from "sonner";
import { useBreadcrumbs } from "@/components/BreadcrumbContext";
import { useConfirm } from "@/components/ConfirmDialog";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Select } from "@/components/ui/select";
import { EvalPageFrame, InlinePanel, evalInputClass } from "@/components/evals/eval-ui";
import { errorMessage, relativeTime } from "@/components/reward-models/rm-text";
import { GateBadge } from "@/components/test-sets/test-set-ui";
import { imGet, imList, type ModelSummary } from "@/lib/intuition-api";
import {
  effectiveBaseline, inputPreview, parseCasesJsonl, pct, runDelta, runHref, tsAddCases, tsDelete, tsDeleteCase, tsGet, tsUpdate, tsUpdateCase,
  type Scorer, type TestCase, type TestSet,
} from "@/lib/test-sets-api";
import { cn } from "@/lib/utils";

// Runs score in the background; poll while one is scoring.
const POLL_MS = 3000;

export default function TestSetClient({ id }: { id: string }) {
  const router = useRouter();
  const confirm = useConfirm();
  const [set, setSet] = useState<TestSet | null>(null);
  const [error, setError] = useState("");
  const [evals, setEvals] = useState<ModelSummary[]>([]);
  const [editing, setEditing] = useState(false);
  useBreadcrumbs([{ label: "Evals", href: "/reward-models/evals" }, { label: "Test sets", href: "/reward-models/evals/test-sets" }, { label: set?.name ?? "Test set" }], `test-set:${id}:${set?.name ?? ""}`);

  const load = useCallback(async () => { try { setSet(await tsGet(id)); setError(""); } catch (e) { setError(errorMessage(e)); } }, [id]);
  useEffect(() => { void load(); }, [load]);
  useEffect(() => { imList().then((r) => setEvals(r.models)).catch(() => setEvals([])); }, []);
  const scoring = !!set?.runs.some((r) => r.status === "scoring");
  useEffect(() => {
    if (!scoring) return;
    const timer = setInterval(() => void load(), POLL_MS);
    return () => clearInterval(timer);
  }, [scoring, load]);

  async function patch(body: Parameters<typeof tsUpdate>[1], success = "Saved") {
    try { await tsUpdate(id, body); await load(); toast.success(success); return true; }
    catch (e) { toast.error(errorMessage(e)); return false; }
  }

  async function remove() {
    if (!set || !await confirm({ title: `Delete "${set.name}"?`, body: "Its cases and runs will be deleted. This cannot be undone.", confirmLabel: "Delete" })) return;
    try { await tsDelete(id); router.push("/reward-models/evals/test-sets"); } catch (e) { toast.error(errorMessage(e)); }
  }

  if (!set) return <EvalPageFrame>{error ? <p role="alert" className="text-xs text-destructive">{error} <button className="underline" onClick={() => void load()}>Retry</button></p> : <p role="status" className="text-xs text-muted-foreground">Loading test set…</p>}</EvalPageFrame>;

  const evalName = (evalId: string) => evals.find((m) => m.id === evalId)?.name ?? "Eval";
  const scoredBy = set.scorers.map((s) => s.type === "expected" ? "Expected answer" : `${evalName(s.eval_id)} (passes: ${s.pass_labels.join(", ")})`).join(" · ");

  return <EvalPageFrame title={set.name} description={set.description || undefined}
    actions={<Button size="sm" variant="ghost" className="text-muted-foreground" onClick={() => void remove()}><Trash2 />Delete</Button>}>
    <p className="-mt-3 mb-6 text-xs text-muted-foreground">
      Scored by: <span className="text-foreground">{scoredBy}</span> · Allowed regressions: <span className="text-foreground tabular-nums">{set.max_regressions}</span>
      <button type="button" className="ml-2 underline hover:text-foreground" onClick={() => setEditing(true)}>Edit</button>
    </p>
    <RunsSection set={set} onBaseline={(runId) => void patch({ baseline_run_id: runId }, "Baseline set")} />
    <CasesSection set={set} onChanged={() => void load()} />
    <CiCard name={set.name} defaultOpen={!set.runs.length} />
    <ScoringDialog open={editing} onOpenChange={setEditing} set={set} evals={evals} onSave={(body) => patch(body)} />
  </EvalPageFrame>;
}

function RunsSection({ set, onBaseline }: { set: TestSet; onBaseline: (runId: string) => void }) {
  const router = useRouter();
  const baseline = effectiveBaseline(set);
  return <section aria-label="Runs" className="mb-8">
    <h2 className="mb-2 text-sm font-semibold">Runs</h2>
    {!set.runs.length ? <p className="rounded border border-dashed border-border px-3 py-6 text-xs text-muted-foreground">No runs yet. Run the set from CI (below) to record your agent’s answers; each run is compared with the one before it.</p>
      : <div className="overflow-x-auto rounded border border-border"><table aria-label="Runs" className="w-full min-w-[720px] text-left text-xs">
        <thead className="border-b border-border bg-surface/60 text-muted-foreground"><tr className="h-8 [&>th]:px-3 [&>th]:font-medium"><th>Run</th><th>When</th><th className="text-right">Passed</th><th className="text-right">Broke</th><th className="text-right">Fixed</th><th>Gate</th><th className="w-36" /></tr></thead>
        <tbody>{set.runs.map((r) => {
          const s = r.summary;
          const delta = runDelta(s);
          const isBaseline = r.id === baseline;
          return <tr key={r.id} className="h-10 cursor-pointer border-b border-border hover:bg-surface/60 [&>td]:px-3" onClick={(event) => {
            if ((event.target as HTMLElement).closest("a,button")) return;
            router.push(runHref(r.id));
          }}>
            <td><Link href={runHref(r.id)} className="font-medium">{r.label || "Unlabeled"}</Link>
              {isBaseline && <span className="ml-2 rounded border border-border px-1 py-px text-[10.5px] text-muted-foreground" title={set.baseline_run_id ? "New runs compare against this run." : "New runs compare against the latest run that passed, until you pick one."}>{set.baseline_run_id ? "baseline" : "baseline (last pass)"}</span>}</td>
            <td className="text-muted-foreground" title={new Date(r.created_at).toLocaleString()}>{relativeTime(r.created_at)}</td>
            <td className="text-right tabular-nums">{r.status === "scoring" ? <span className="text-muted-foreground">Scoring…</span>
              : r.status === "failed" ? <span className="text-destructive" title={r.error ?? undefined}>Failed</span>
              : s ? <>{s.passed}/{s.cases} ({pct(s.pass_rate)}){delta !== null && delta !== 0 && <span className={cn("ml-1.5", delta < 0 ? "text-destructive" : "text-success")}>{delta > 0 ? "+" : "−"}{Math.round(Math.abs(delta) * 100)} pts</span>}</> : "—"}</td>
            <td className={cn("text-right tabular-nums", s?.broke.length ? "font-medium text-destructive" : "text-muted-foreground")}>{s?.baseline ? s.broke.length : "—"}</td>
            <td className={cn("text-right tabular-nums", s?.fixed.length ? "font-medium text-success" : "text-muted-foreground")}>{s?.baseline ? s.fixed.length : "—"}</td>
            <td>{s?.baseline ? <GateBadge gate={s.gate} /> : <span className="text-muted-foreground" title="The first run has nothing to compare with.">—</span>}</td>
            <td className="text-right">{!isBaseline && r.status === "done" && <Button size="xs" variant="ghost" className="text-muted-foreground" onClick={() => onBaseline(r.id)}>Use as baseline</Button>}</td>
          </tr>;
        })}</tbody>
      </table></div>}
  </section>;
}

function InputPreview({ input }: { input: TestCase["input"] }) {
  const { text, earlier } = inputPreview(input);
  return <span className="flex min-w-0 items-baseline gap-1.5"><span className="truncate" title={text}>{text}</span>{earlier > 0 && <span className="shrink-0 text-[11px] text-muted-foreground">+{earlier} turn{earlier === 1 ? "" : "s"}</span>}</span>;
}

function ExpectedCell({ setId, item, onSaved }: { setId: string; item: TestCase; onSaved: () => void }) {
  const [draft, setDraft] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  async function save() {
    if (draft === null || draft.trim() === (item.expected ?? "")) { setDraft(null); return; }
    setBusy(true);
    try { await tsUpdateCase(setId, item.id, { expected: draft.trim() || null }); setDraft(null); onSaved(); }
    catch (e) { toast.error(errorMessage(e)); } finally { setBusy(false); }
  }
  if (draft !== null) return <textarea autoFocus aria-label={`Expected answer for ${item.name || "case"}`} rows={3} disabled={busy} value={draft} className={evalInputClass}
    onChange={(e) => setDraft(e.target.value)} onBlur={() => void save()}
    onKeyDown={(e) => { if (e.key === "Escape") setDraft(null); if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) void save(); }} />;
  return <button type="button" title="Edit expected answer" onClick={() => setDraft(item.expected ?? "")}
    className={cn("block w-full truncate rounded px-1 py-0.5 -mx-1 text-left hover:bg-surface", !item.expected && "text-muted-foreground italic")}>{item.expected || "No expected answer"}</button>;
}

function CasesSection({ set, onChanged }: { set: TestSet; onChanged: () => void }) {
  const confirm = useConfirm();
  const [adding, setAdding] = useState(false);
  const file = useRef<HTMLInputElement>(null);

  async function importFile(f: File) {
    try {
      const cases = parseCasesJsonl(await f.text());
      if (!cases.length) { toast.error("The file has no cases"); return; }
      await tsAddCases(set.id, cases);
      toast.success(`Added ${cases.length} case${cases.length === 1 ? "" : "s"}`);
      onChanged();
    } catch (e) { toast.error(errorMessage(e)); }
  }
  async function remove(c: TestCase) {
    if (!await confirm({ title: `Delete "${c.name || "this case"}"?`, body: "Past runs keep their results.", confirmLabel: "Delete" })) return;
    try { await tsDeleteCase(set.id, c.id); onChanged(); } catch (e) { toast.error(errorMessage(e)); }
  }

  return <section aria-label="Cases" className="mb-8">
    <div className="mb-2 flex items-center gap-2">
      <h2 className="text-sm font-semibold">Cases <span className="font-normal text-muted-foreground tabular-nums">{set.cases.length}</span></h2>
      <div className="ml-auto flex gap-2">
        <Button size="xs" variant="outline" onClick={() => file.current?.click()}><Upload />Import JSONL</Button>
        <Button size="xs" variant="outline" onClick={() => setAdding(true)}><Plus />Add case</Button>
        <input ref={file} type="file" accept=".jsonl,.ndjson,.json,application/json" className="hidden" aria-label="JSONL file"
          onChange={(e) => { const f = e.target.files?.[0]; e.target.value = ""; if (f) void importFile(f); }} />
      </div>
    </div>
    {adding && <AddCaseForm setId={set.id} onClose={() => setAdding(false)} onAdded={onChanged} />}
    {!set.cases.length ? <p className="rounded border border-dashed border-border px-3 py-6 text-xs text-muted-foreground">
      No cases yet. Open a production trace and choose <span className="text-foreground">Add to test set</span>, add one by hand, or import a JSONL file with one <code className="text-[11px]">{"{\"name\", \"input\", \"expected\"}"}</code> per line.
    </p> : <div className="overflow-x-auto rounded border border-border"><table aria-label="Cases" className="w-full min-w-[760px] table-fixed text-left text-xs">
      <thead className="border-b border-border bg-surface/60 text-muted-foreground"><tr className="h-8 [&>th]:px-3 [&>th]:font-medium"><th className="w-48">Case</th><th>Input</th><th>Expected answer</th><th className="w-24" /></tr></thead>
      <tbody>{set.cases.map((c) => <tr key={c.id} className="h-10 border-b border-border align-middle hover:bg-surface/40 [&>td]:px-3 [&>td]:py-1.5">
        <td className="truncate font-medium" title={c.name}>{c.name || <span className="text-muted-foreground">Untitled</span>}</td>
        <td><InputPreview input={c.input} /></td>
        <td><ExpectedCell setId={set.id} item={c} onSaved={onChanged} /></td>
        <td className="text-right whitespace-nowrap">
          {c.source_trace_id && <Link href={`/reward-models/traces/${c.source_trace_id}`} className="mr-1 text-muted-foreground hover:text-foreground hover:underline">Trace</Link>}
          <Button size="icon-xs" variant="ghost" aria-label={`Delete ${c.name || "case"}`} title="Delete" onClick={() => void remove(c)}><Trash2 /></Button>
        </td>
      </tr>)}</tbody>
    </table></div>}
  </section>;
}

function AddCaseForm({ setId, onClose, onAdded }: { setId: string; onClose: () => void; onAdded: () => void }) {
  const [name, setName] = useState("");
  const [input, setInput] = useState("");
  const [expected, setExpected] = useState("");
  const [busy, setBusy] = useState(false);
  async function add() {
    setBusy(true);
    try { await tsAddCases(setId, [{ name: name.trim(), input: input.trim(), expected: expected.trim() || null }]); onAdded(); setName(""); setInput(""); setExpected(""); toast.success("Case added"); }
    catch (e) { toast.error(errorMessage(e)); } finally { setBusy(false); }
  }
  return <InlinePanel title="Add case" onClose={onClose} disabled={busy} className="mb-3">
    <form className="grid gap-3 text-xs" onSubmit={(e) => { e.preventDefault(); if (input.trim() && !busy) void add(); }}>
      <label className="grid gap-1"><span className="font-medium">Name</span><input className={evalInputClass} value={name} maxLength={200} onChange={(e) => setName(e.target.value)} placeholder="refund window" /></label>
      <div className="grid gap-3 md:grid-cols-2">
        <label className="grid gap-1"><span className="font-medium">Input</span><textarea autoFocus className={evalInputClass} rows={4} value={input} onChange={(e) => setInput(e.target.value)} placeholder="What the user says" /></label>
        <label className="grid gap-1"><span className="font-medium">Expected answer</span><textarea className={evalInputClass} rows={4} value={expected} maxLength={20_000} onChange={(e) => setExpected(e.target.value)} placeholder="What the agent should answer" /></label>
      </div>
      <div><Button size="sm" type="submit" disabled={!input.trim() || busy}>{busy ? "Adding…" : "Add case"}</Button></div>
    </form>
  </InlinePanel>;
}

export function ciCommand(name: string) {
  return `stash test run ${JSON.stringify(name)} --command "python agent.py"`;
}

function CiCard({ name, defaultOpen }: { name: string; defaultOpen: boolean }) {
  const [open, setOpen] = useState(defaultOpen);
  const command = ciCommand(name);
  const workflow = `- name: Regression tests
  env:
    STASH_API_KEY: \${{ secrets.STASH_API_KEY }}
  run: |
    pip install stashai
    ${command}`;
  return <section aria-label="Run in CI" className="rounded border border-border">
    <button type="button" aria-expanded={open} onClick={() => setOpen(!open)} className="flex w-full items-center gap-1.5 px-3 py-2 text-left text-sm font-semibold">
      {open ? <ChevronDown className="size-3.5" /> : <ChevronRight className="size-3.5" />}Run in CI
    </button>
    {open && <div className="grid gap-3 border-t border-border px-3 py-3 text-xs">
      <p className="text-muted-foreground">Stash sends each case’s input to your command on stdin and reads the answer from stdout. The command exits 1 when the run breaks more cases than you allow.</p>
      <Snippet text={command} />
      <p className="text-muted-foreground">In a GitHub Actions job:</p>
      <Snippet text={workflow} />
    </div>}
  </section>;
}

function Snippet({ text }: { text: string }) {
  return <div className="group relative"><pre className="overflow-x-auto rounded bg-surface px-3 py-2 text-[11.5px] leading-5" style={{ fontFamily: "ui-monospace, SFMono-Regular, Menlo, monospace" }}>{text}</pre>
    <Button size="xs" variant="outline" className="absolute top-1.5 right-1.5 opacity-0 group-hover:opacity-100 focus-visible:opacity-100"
      onClick={() => { void navigator.clipboard.writeText(text).then(() => toast.success("Copied")); }}>Copy</Button></div>;
}

type EvalScorer = Extract<Scorer, { type: "eval" }>;

function ScoringDialog({ open, onOpenChange, set, evals, onSave }: {
  open: boolean; onOpenChange: (open: boolean) => void; set: TestSet; evals: ModelSummary[];
  onSave: (body: { scorers: Scorer[]; max_regressions: number }) => Promise<boolean>;
}) {
  const [expected, setExpected] = useState(true);
  const [evalScorers, setEvalScorers] = useState<EvalScorer[]>([]);
  const [allowed, setAllowed] = useState("0");
  const [labels, setLabels] = useState<Record<string, string[]>>({});
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (!open) return;
    setExpected(set.scorers.some((s) => s.type === "expected"));
    setEvalScorers(set.scorers.filter((s): s is EvalScorer => s.type === "eval"));
    setAllowed(String(set.max_regressions));
  }, [open, set]);

  const wanted = evalScorers.map((s) => s.eval_id).filter((evalId) => evalId && !labels[evalId]).join(",");
  useEffect(() => {
    if (!wanted) return;
    for (const evalId of wanted.split(",")) {
      imGet(evalId).then((d) => setLabels((cur) => ({ ...cur, [evalId]: (d.active ?? d.draft)?.labels.map((l) => l.id) ?? [] })))
        .catch((e) => toast.error(errorMessage(e)));
    }
  }, [wanted]);

  const choices = evals.filter((m) => m.output_type === "choice" && m.active_version_id);
  const scorers: Scorer[] = [...(expected ? [{ type: "expected" as const }] : []), ...evalScorers];
  const valid = scorers.length > 0 && evalScorers.every((s) => s.eval_id && s.pass_labels.length) && /^\d+$/.test(allowed);
  const update = (i: number, next: Partial<EvalScorer>) => setEvalScorers((cur) => cur.map((s, j) => j === i ? { ...s, ...next } : s));

  return <Dialog open={open} onOpenChange={onOpenChange}><DialogContent className="max-w-lg">
    <DialogHeader><DialogTitle>Scoring</DialogTitle><DialogDescription>A case passes when every scorer passes it.</DialogDescription></DialogHeader>
    <div className="grid gap-4 text-xs">
      <label className="flex items-start gap-2"><input type="checkbox" className="mt-0.5" checked={expected} onChange={(e) => setExpected(e.target.checked)} />
        <span><span className="font-medium">Expected answer</span><span className="block text-muted-foreground">Passes when the answer says the same thing as the case’s expected answer.</span></span></label>
      {evalScorers.map((s, i) => <div key={i} className="grid gap-2 rounded border border-border p-3">
        <div className="flex items-center gap-2">
          <Select aria-label="Eval" value={s.eval_id} onChange={(v) => update(i, { eval_id: v, pass_labels: [] })} options={choices.map((m) => ({ value: m.id, label: m.name }))} className="h-7 min-w-0 flex-1 px-2 text-xs" />
          <Button size="icon-xs" variant="ghost" aria-label="Remove eval" onClick={() => setEvalScorers((cur) => cur.filter((_, j) => j !== i))}><X /></Button>
        </div>
        {s.eval_id && <div className="flex flex-wrap items-center gap-x-3 gap-y-1"><span className="text-muted-foreground">Passes:</span>
          {(labels[s.eval_id] ?? []).map((l) => <label key={l} className="inline-flex items-center gap-1"><input type="checkbox" checked={s.pass_labels.includes(l)}
            onChange={(e) => update(i, { pass_labels: e.target.checked ? [...s.pass_labels, l] : s.pass_labels.filter((x) => x !== l) })} />{l}</label>)}
          {!labels[s.eval_id] && <span className="text-muted-foreground">Loading labels…</span>}
        </div>}
      </div>)}
      <div><Button size="xs" variant="outline" disabled={!choices.length} title={choices.length ? undefined : "Save a label eval first"}
        onClick={() => setEvalScorers((cur) => [...cur, { type: "eval", eval_id: choices[0]?.id ?? "", pass_labels: [] }])}><Plus />Add eval</Button></div>
      <label className="grid gap-1"><span className="font-medium">Allowed regressions</span>
        <input type="number" min={0} className={cn(evalInputClass, "w-24")} value={allowed} onChange={(e) => setAllowed(e.target.value)} />
        <span className="text-[11px] text-muted-foreground">A run fails when more cases than this go from passing to failing.</span></label>
    </div>
    <DialogFooter><Button size="sm" variant="outline" onClick={() => onOpenChange(false)}>Cancel</Button>
      <Button size="sm" disabled={!valid || busy} onClick={async () => { setBusy(true); if (await onSave({ scorers, max_regressions: Number(allowed) })) onOpenChange(false); setBusy(false); }}>{busy ? "Saving…" : "Save"}</Button></DialogFooter>
  </DialogContent></Dialog>;
}
