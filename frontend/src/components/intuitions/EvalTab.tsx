"use client";

import { Fragment, useMemo, useRef, useState } from "react";
import { Check, ChevronRight, FileUp, ListChecks, Play, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { errorMessage } from "@/components/reward-models/rm-text";
import { cn } from "@/lib/utils";
import { imBatch, type BatchResponse, type BatchRow, type Item, type Version } from "@/lib/intuition-api";
import { examplesToJsonl, isFlagged, itemSummary, MAX_BATCH, num, parseBatchInput, pct, signed } from "./im-helpers";
import { Bar, Callout, FlagTag, inputClass, Metric, MetricGrid, Panel, Segmented, Spinner, useIntuition } from "./im-ui";
import DriverBars from "./DriverBars";
import ItemView from "./ItemView";

type Which = "active" | "draft";
type Filter = "all" | "mistakes" | "flagged";

function servable(v: Version | null): boolean {
  return !!v && !!v.head && !v.head_stale;
}

const PLACEHOLDER = [
  '{"item": {"customer": "…", "reply": "…"}, "label": "send"}',
  '{"item": "plain text item", "label": "edit"}',
  '"an unlabeled item as a JSON string"',
  "or plain text, one item per line",
].join("\n");

export default function EvalTab() {
  const { id, detail, examples, goTo } = useIntuition();
  const outputType = detail.model.output_type;
  const canActive = servable(detail.active);
  const canDraft = servable(detail.draft);
  const [which, setWhich] = useState<Which>(canActive || !canDraft ? "active" : "draft");
  const version = which === "draft" ? detail.draft : detail.active;
  const labels = useMemo(() => version?.labels ?? [], [version]);
  const allowed = useMemo(() => (outputType === "choice" ? labels.map((l) => l.id) : ["good", "bad"]), [outputType, labels]);
  const [text, setText] = useState("");
  const [log, setLog] = useState(false);
  const [running, setRunning] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<{ response: BatchResponse; items: Item[] } | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);

  const parsed = useMemo(() => parseBatchInput(text, allowed), [text, allowed]);
  const labeled = parsed.labels.filter((l) => l !== null).length;
  const heldOut = (examples ?? []).filter((e) => e.split === "eval" && e.item_b == null && e.label && !e.needs_review);

  async function run() {
    if (parsed.errors.length || parsed.items.length === 0) return;
    setRunning(true);
    setError(null);
    try {
      const response = await imBatch(id, { items: parsed.items, labels: labeled ? parsed.labels : undefined, version: which, log });
      setResult({ response, items: parsed.items });
    } catch (e) {
      setError(errorMessage(e));
    } finally {
      setRunning(false);
    }
  }

  async function loadFile(file: File) {
    if (file.size > 5_000_000) return setError("File is larger than 5 MB");
    setError(null);
    setText((await file.text()).replace(/\r\n/g, "\n"));
  }

  if (!canActive && !canDraft) {
    return (
      <Callout tone="info" action={<Button size="sm" onClick={() => goTo("train")}>Go to Train</Button>}>
        Nothing to evaluate yet: fit a head on the Train tab first.
      </Callout>
    );
  }

  return (
    <div className="space-y-4">
      <Panel
        title="Run an eval"
        description="Run the model over a dataset, the way an agent would with stash_intuition_batch. Items the judge hasn’t seen are graded by Jev; cached answers are free."
        actions={
          <Segmented
            size="xs"
            ariaLabel="Version"
            value={which}
            onChange={(v) => {
              setWhich(v);
              setResult(null);
            }}
            options={[
              ...(canActive ? [{ value: "active" as const, label: `Active v${detail.active?.number}` }] : []),
              ...(canDraft ? [{ value: "draft" as const, label: `Draft v${detail.draft?.number}` }] : []),
            ]}
          />
        }
      >
        <form
          className="space-y-2.5"
          onSubmit={(e) => {
            e.preventDefault();
            void run();
          }}
        >
          <textarea
            aria-label="Eval items, one per line"
            rows={8}
            value={text}
            onChange={(e) => setText(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) {
                e.preventDefault();
                void run();
              }
            }}
            spellCheck={false}
            placeholder={PLACEHOLDER}
            aria-invalid={parsed.errors.length ? true : undefined}
            className={cn(inputClass, "resize-y font-mono text-[11.5px] leading-relaxed whitespace-pre")}
          />
          <div className="flex flex-wrap items-center gap-2">
            <input
              ref={fileRef}
              type="file"
              accept=".jsonl,.ndjson,.json,.txt,application/json,text/plain"
              className="hidden"
              aria-label="Upload a JSONL file"
              onChange={(e) => {
                const file = e.target.files?.[0];
                if (file) void loadFile(file);
                e.target.value = "";
              }}
            />
            <Button type="button" variant="outline" size="sm" onClick={() => fileRef.current?.click()} disabled={running}>
              <FileUp /> Upload .jsonl
            </Button>
            {heldOut.length > 0 && (
              <Button
                type="button"
                variant="ghost"
                size="sm"
                disabled={running}
                onClick={() => setText(examplesToJsonl(heldOut.slice(0, MAX_BATCH)))}
                title="Fill with your labeled held-out examples (cached answers, so free)"
              >
                <ListChecks /> Use held-out examples · {heldOut.length}
              </Button>
            )}
            <span className="flex-1" />
            <label className="inline-flex items-center gap-1.5 text-[12px] text-dim" title="Also log each prediction to the review inbox">
              <input type="checkbox" checked={log} onChange={(e) => setLog(e.target.checked)} className="accent-brand-500" />
              Log to inbox
            </label>
            <Button type="submit" size="sm" disabled={running || parsed.errors.length > 0 || parsed.items.length === 0}>
              {running ? <Spinner /> : <Play />}
              Run eval
            </Button>
          </div>
          <p className="m-0 text-[11.5px] text-muted-foreground">
            {parsed.items.length === 0 && parsed.errors.length === 0 ? (
              <>
                One item per line: <code className="font-mono">{'{"item": …, "label": …}'}</code> (label optional; one of {allowed.join(", ")}), a JSON string, or plain text. Up to {MAX_BATCH}.
              </>
            ) : (
              <>
                <span className="font-mono text-foreground">{parsed.items.length}</span> item{parsed.items.length === 1 ? "" : "s"} · <span className="font-mono text-foreground">{labeled}</span> labeled
                {labeled === 0 && " — add labels to get accuracy, log loss and Brier"}
              </>
            )}
          </p>
          {parsed.errors.length > 0 && (
            <Callout tone="danger">
              <ul className="m-0 list-none space-y-0.5 p-0 font-mono text-[11.5px]">
                {parsed.errors.slice(0, 6).map((e) => (
                  <li key={e}>{e}</li>
                ))}
                {parsed.errors.length > 6 && <li>…and {parsed.errors.length - 6} more</li>}
              </ul>
            </Callout>
          )}
          {error && <Callout tone="danger">{error}</Callout>}
        </form>
      </Panel>

      {result && <EvalResults response={result.response} items={result.items} rubric={version?.rubric ?? []} isFlaggedLabel={(l) => (outputType === "choice" ? isFlagged(labels, l) : l === "bad")} />}
    </div>
  );
}

function EvalResults({ response, items, rubric, isFlaggedLabel }: { response: BatchResponse; items: Item[]; rubric: Version["rubric"]; isFlaggedLabel: (label: string) => boolean }) {
  const { summary, results } = response;
  const [filter, setFilter] = useState<Filter>("all");
  const [open, setOpen] = useState<number | null>(null);
  const counts = Object.entries(summary.label_counts).sort((a, b) => b[1] - a[1]);
  const mistakes = results.filter((r) => r.correct === false).length;
  const rows = results.map((r, i) => ({ r, i })).filter(({ r }) => (filter === "mistakes" ? r.correct === false : filter === "flagged" ? isFlaggedLabel(r.label) : true));

  return (
    <Panel
      title={`Results · v${response.version}`}
      actions={
        <Segmented
          size="xs"
          ariaLabel="Filter rows"
          value={filter}
          onChange={setFilter}
          options={[
            { value: "all", label: `All · ${results.length}` },
            ...(summary.labeled ? [{ value: "mistakes" as const, label: `Mistakes · ${mistakes}` }] : []),
            { value: "flagged", label: `Flagged · ${summary.flagged}` },
          ]}
        />
      }
    >
      <div className="space-y-3">
        <MetricGrid className={summary.labeled ? "sm:grid-cols-6" : "sm:grid-cols-3"}>
          <Metric label="Items" value={String(summary.n)} hint={summary.labeled ? `${summary.labeled} labeled` : "unlabeled"} />
          <Metric label="Mean confidence" value={pct(summary.mean_confidence, 1)} />
          <Metric label="Flagged" value={String(summary.flagged)} hint="needs-fixing verdicts" />
          {summary.labeled ? (
            <>
              <Metric label="Accuracy" value={pct(summary.accuracy, 1)} emphasis />
              <Metric label="Log loss" value={num(summary.log_loss)} hint="lower is better" />
              <Metric label="Brier" value={num(summary.brier)} hint="lower is better" />
            </>
          ) : null}
        </MetricGrid>
        <div className="max-w-md space-y-1">
          {counts.map(([label, n]) => (
            <div key={label} className="grid grid-cols-[minmax(4rem,8rem)_1fr_4.5rem] items-center gap-2.5">
              <span className="flex min-w-0 items-center gap-1 font-mono text-[12px] text-dim">
                <span className="truncate">{label}</span>
                {isFlaggedLabel(label) && <FlagTag label="" className="px-1" />}
              </span>
              <Bar value={n / summary.n} className="h-2" />
              <span className="text-right font-mono text-[11.5px] tabular-nums text-muted-foreground">
                {n} · {pct(n / summary.n)}
              </span>
            </div>
          ))}
        </div>
        <div className="overflow-x-auto rounded-md border border-border-subtle">
          <table className="w-full min-w-[44rem] border-collapse text-[12px]">
            <thead>
              <tr className="border-b border-border-subtle bg-surface/60 text-left text-[10.5px] tracking-wide text-muted-foreground uppercase">
                <th className="w-8 px-2 py-1.5 font-medium">#</th>
                <th className="px-2 py-1.5 font-medium">Item</th>
                <th className="w-32 px-2 py-1.5 font-medium">Predicted</th>
                <th className="w-14 px-2 py-1.5 text-right font-medium">Conf.</th>
                <th className="w-24 px-2 py-1.5 font-medium">Expected</th>
                <th className="w-56 px-2 py-1.5 font-medium">Top reason</th>
              </tr>
            </thead>
            <tbody>
              {rows.length === 0 && (
                <tr>
                  <td colSpan={6} className="px-3 py-4 text-center text-[12px] text-muted-foreground">
                    No rows match this filter.
                  </td>
                </tr>
              )}
              {rows.map(({ r, i }) => (
                <Fragment key={i}>
                  <ResultRow index={i} row={r} item={items[i]} open={open === i} flagged={isFlaggedLabel(r.label)} onToggle={() => setOpen(open === i ? null : i)} />
                  {open === i && (
                    <tr className="border-b border-border-subtle bg-surface/30">
                      <td />
                      <td colSpan={5} className="px-2 py-3">
                        <div className="grid gap-4 lg:grid-cols-2">
                          <ItemView item={items[i]} />
                          <div>
                            <div className="mb-1.5 text-[11.5px] font-medium text-dim">
                              Why “{r.label}” (top {r.drivers.length})
                            </div>
                            <DriverBars drivers={r.drivers} rubric={rubric} compact />
                          </div>
                        </div>
                      </td>
                    </tr>
                  )}
                </Fragment>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </Panel>
  );
}

function ResultRow({ index, row, item, open, flagged, onToggle }: { index: number; row: BatchRow; item: Item; open: boolean; flagged: boolean; onToggle: () => void }) {
  const top = row.drivers[0];
  return (
    <tr className={cn("cursor-pointer border-b border-border-subtle align-top hover:bg-muted/40", row.correct === false && "bg-red-500/[0.03]")} onClick={onToggle}>
      <td className="px-2 py-1.5 font-mono text-[11px] text-muted-foreground tabular-nums">
        <button
          type="button"
          aria-expanded={open}
          aria-label={`Details for item ${index + 1}`}
          className="inline-flex items-center"
          onClick={(e) => {
            e.stopPropagation();
            onToggle();
          }}
        >
          <ChevronRight className={cn("h-3 w-3 transition-transform", open && "rotate-90")} />
          {index + 1}
        </button>
      </td>
      <td className="max-w-0 px-2 py-1.5">
        <div className="truncate text-foreground" title={itemSummary(item).slice(0, 600)}>
          {itemSummary(item)}
        </div>
      </td>
      <td className="px-2 py-1.5">
        <span className="inline-flex items-center gap-1">
          <span className="font-mono text-foreground">{row.label}</span>
          {flagged && <FlagTag label="" className="px-1" />}
        </span>
      </td>
      <td className="px-2 py-1.5 text-right font-mono tabular-nums text-muted-foreground">{pct(row.confidence)}</td>
      <td className="px-2 py-1.5">
        {row.expected ? (
          <span className={cn("inline-flex items-center gap-1 font-mono", row.correct ? "text-emerald-700 dark:text-emerald-400" : "text-red-600 dark:text-red-400")}>
            {row.correct ? <Check className="h-3 w-3" aria-label="correct" /> : <X className="h-3 w-3" aria-label="wrong" />}
            {row.expected}
          </span>
        ) : (
          <span className="text-muted-foreground">—</span>
        )}
      </td>
      <td className="max-w-0 px-2 py-1.5">
        {top ? (
          <div className="flex min-w-0 items-baseline gap-1.5" title={top.prompt}>
            <span className={cn("shrink-0 font-mono text-[11px] tabular-nums", top.contribution >= 0 ? "text-emerald-700 dark:text-emerald-400" : "text-red-600 dark:text-red-400")}>{signed(top.contribution)}</span>
            <span className="truncate font-mono text-[11px] text-dim">{top.question_id}</span>
          </div>
        ) : (
          <span className="text-muted-foreground">—</span>
        )}
      </td>
    </tr>
  );
}
