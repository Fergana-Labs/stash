"use client";

import Link from "next/link";
import { useState } from "react";
import { CheckCircle2, ChevronRight, Search, ShieldCheck, TriangleAlert } from "lucide-react";
import { Button } from "@/components/ui/button";
import { errorMessage } from "@/components/reward-models/rm-text";
import { cn } from "@/lib/utils";
import { imCheck, imFind, type CheckResponse, type FoundModel, type Item, type ModelSummary } from "@/lib/intuition-api";
import { parseItemJson, pct } from "./im-helpers";
import { Callout, FlagTag, inputClass, Segmented, Spinner } from "./im-ui";
import DriverBars from "./DriverBars";

const MAX_MODELS = 8;

/** Text, or a JSON object when the input looks like one. */
function toItem(text: string): { item: Item } | { error: string } {
  const trimmed = text.trim();
  if (!trimmed) return { error: "Paste the output to check" };
  if (trimmed.startsWith("{")) return parseItemJson(trimmed);
  return { item: trimmed };
}

/**
 * Try what an agent does before finishing: lint one output with your models (picked, or
 * routed from a task description) and see each verdict, what it flags, and why.
 */
export default function CheckPanel({ models }: { models: ModelSummary[] }) {
  const servable = models.filter((m) => m.active_version_id);
  const [text, setText] = useState("");
  const [mode, setMode] = useState<"pick" | "task">("pick");
  const [picked, setPicked] = useState<Set<string>>(new Set());
  const [task, setTask] = useState("");
  const [busy, setBusy] = useState<"check" | "find" | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<CheckResponse | null>(null);
  const [found, setFound] = useState<FoundModel[] | null>(null);
  const names = new Map(models.map((m) => [m.id, m.name]));

  async function check() {
    const parsed = toItem(text);
    if ("error" in parsed) return setError(parsed.error);
    if (mode === "pick" && picked.size === 0) return setError("Pick at least one model");
    if (mode === "task" && !task.trim()) return setError("Describe the task the output is for");
    setBusy("check");
    setError(null);
    setFound(null);
    try {
      setResult(await imCheck(mode === "pick" ? { item: parsed.item, model_ids: [...picked] } : { item: parsed.item, task: task.trim() }));
    } catch (e) {
      setResult(null);
      setError(errorMessage(e));
    } finally {
      setBusy(null);
    }
  }

  async function find() {
    if (!task.trim()) return setError("Describe the task first");
    setBusy("find");
    setError(null);
    try {
      setFound((await imFind(task.trim())).models);
    } catch (e) {
      setFound(null);
      setError(errorMessage(e));
    } finally {
      setBusy(null);
    }
  }

  return (
    <details className="group rounded-lg border border-border bg-background">
      <summary className="flex cursor-pointer list-none flex-wrap items-center gap-1.5 px-4 py-2.5 text-[13px] font-medium text-foreground select-none [&::-webkit-details-marker]:hidden">
        <ChevronRight className="h-3.5 w-3.5 text-muted-foreground transition-transform group-open:rotate-90" />
        <ShieldCheck className="h-3.5 w-3.5 text-muted-foreground" />
        Check an output
        <span className="ml-1 text-[12px] font-normal text-muted-foreground">What an agent does before finishing: lint its work with your judgments.</span>
      </summary>
      <form
        className="space-y-2.5 border-t border-border-subtle px-4 py-3"
        onSubmit={(e) => {
          e.preventDefault();
          void check();
        }}
      >
        <textarea
          aria-label="Output to check"
          rows={4}
          value={text}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) {
              e.preventDefault();
              void check();
            }
          }}
          placeholder={'The output to check: plain text, or a JSON object like {"customer": "…", "reply": "…"}'}
          className={cn(inputClass, "resize-y leading-relaxed")}
        />
        <div className="flex flex-wrap items-center gap-2">
          <Segmented
            size="xs"
            ariaLabel="How to choose models"
            value={mode}
            onChange={(m) => {
              setMode(m);
              setError(null);
            }}
            options={[
              { value: "pick", label: "Pick models" },
              { value: "task", label: "Route by task" },
            ]}
          />
          <span className="text-[11.5px] text-muted-foreground">{mode === "pick" ? `Up to ${MAX_MODELS}, active versions only.` : "Claude picks the models whose “when to use” fits the task."}</span>
        </div>
        {mode === "pick" ? (
          servable.length === 0 ? (
            <p className="m-0 text-[12px] text-muted-foreground">No model has an active version yet. Load an example or promote a version first.</p>
          ) : (
            <div className="flex flex-wrap gap-1.5" role="group" aria-label="Models to check with">
              {servable.map((m) => {
                const on = picked.has(m.id);
                return (
                  <label
                    key={m.id}
                    className={cn(
                      "inline-flex max-w-full cursor-pointer items-center gap-1.5 rounded-md border px-2 py-1 text-[12px] transition-colors",
                      on ? "border-brand-400 bg-brand-500/8 text-foreground" : "border-border text-dim hover:border-brand-300",
                    )}
                  >
                    <input
                      type="checkbox"
                      checked={on}
                      disabled={!on && picked.size >= MAX_MODELS}
                      onChange={(e) =>
                        setPicked((prev) => {
                          const next = new Set(prev);
                          if (e.target.checked) next.add(m.id);
                          else next.delete(m.id);
                          return next;
                        })
                      }
                      className="accent-brand-500"
                    />
                    <span className="truncate">{m.name}</span>
                  </label>
                );
              })}
            </div>
          )
        ) : (
          <div className="flex flex-wrap items-center gap-2">
            <input
              aria-label="Task description"
              value={task}
              onChange={(e) => setTask(e.target.value)}
              maxLength={4000}
              placeholder="e.g. Reply to a customer asking for a refund"
              className={cn(inputClass, "min-w-0 flex-1 basis-64")}
            />
            <Button type="button" variant="ghost" size="sm" onClick={() => void find()} disabled={busy !== null} title="See which models would be consulted, without running them">
              {busy === "find" ? <Spinner /> : <Search />}
              Which apply?
            </Button>
          </div>
        )}
        <div className="flex flex-wrap items-center gap-2">
          <Button type="submit" size="sm" disabled={busy !== null}>
            {busy === "check" ? <Spinner /> : <ShieldCheck />}
            Run check
          </Button>
          <span className="text-[11.5px] text-muted-foreground">New items are graded by Jev; results are logged to each model’s Inbox.</span>
        </div>
        {error && <Callout tone="danger">{error}</Callout>}
        {found && <Routed models={found} />}
        {result && <CheckResult result={result} names={names} />}
      </form>
    </details>
  );
}

function Routed({ models, title = "Would consult" }: { models: FoundModel[]; title?: string }) {
  if (models.length === 0) return <p className="m-0 text-[12px] text-muted-foreground">No model’s “when to use” matches this task.</p>;
  return (
    <div>
      <p className="m-0 mb-1 text-[11.5px] font-medium text-dim">{title}</p>
      <ul className="m-0 list-none space-y-1 p-0">
        {models.map((m) => (
          <li key={m.model_id} className="text-[12px] leading-snug">
            <Link href={`/reward-models/intuitions/${m.model_id}`} className="font-medium text-foreground hover:text-brand-600">
              {m.name}
            </Link>
            <span className="text-muted-foreground"> — {m.reason}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}

function CheckResult({ result, names }: { result: CheckResponse; names: Map<string, string> }) {
  const ran = result.results.length;
  return (
    <div className="space-y-2.5 rounded-md border border-border-subtle bg-surface/30 p-3">
      <div className={cn("flex items-center gap-2 text-[13px] font-medium", ran === 0 ? "text-muted-foreground" : result.passed ? "text-emerald-700 dark:text-emerald-400" : "text-red-600 dark:text-red-400")}>
        {result.passed ? <CheckCircle2 className="h-4 w-4" /> : <TriangleAlert className="h-4 w-4" />}
        {ran === 0
          ? "No model ran"
          : result.passed
            ? `Passed — none of ${ran} model${ran === 1 ? "" : "s"} flagged it`
            : `${result.findings.length} finding${result.findings.length === 1 ? "" : "s"} from ${ran} model${ran === 1 ? "" : "s"}`}
      </div>
      {result.routed && <Routed models={result.routed} title="Routed to" />}
      <ul className="m-0 list-none space-y-2 p-0">
        {result.results.map((r) => (
          <li key={r.model_id} className={cn("rounded-md border bg-background px-3 py-2", r.flagged ? "border-red-500/30" : "border-border-subtle")}>
            <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
              <Link href={`/reward-models/intuitions/${r.model_id}?tab=inbox`} className="min-w-0 truncate text-[12.5px] font-medium text-foreground hover:text-brand-600">
                {r.name}
              </Link>
              <span className="font-mono text-[12px] font-semibold text-foreground">{r.label}</span>
              {r.flagged && <FlagTag />}
              <span className="text-[11.5px] text-muted-foreground">
                <span className="font-mono text-foreground">{pct(r.confidence)}</span> confident
              </span>
            </div>
            {r.label_meaning && <p className="m-0 mt-0.5 text-[12px] text-muted-foreground">{r.label_meaning}</p>}
            {r.why.length > 0 && (
              <div className="mt-2">
                <p className="m-0 mb-1 text-[11px] font-medium text-dim">Why “{r.label}”</p>
                <DriverBars drivers={r.why} compact limit={3} />
              </div>
            )}
          </li>
        ))}
      </ul>
      {result.errors.length > 0 && (
        <Callout tone="danger">
          <ul className="m-0 list-none space-y-0.5 p-0 text-[12px]">
            {result.errors.map((e) => (
              <li key={e.model_id}>
                <span className="font-medium">{names.get(e.model_id) ?? e.model_id}</span>: {e.error}
              </li>
            ))}
          </ul>
        </Callout>
      )}
    </div>
  );
}
