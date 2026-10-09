"use client";

import { useCallback, useEffect, useState } from "react";
import { Check, X } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { RmListSkeleton } from "@/components/reward-models/RmSkeletons";
import { EmptyState } from "@/components/reward-models/rm-ui";
import { errorMessage, relativeTime } from "@/components/reward-models/rm-text";
import { cn } from "@/lib/utils";
import { imPredictions, imReview, type LoggedPrediction } from "@/lib/intuition-api";
import { allowedLabels, labelText, pct } from "./im-helpers";
import { LabelTag, LoadError, Segmented, useIntuition } from "./im-ui";
import ItemView from "./ItemView";

type Status = "unreviewed" | "labeled" | "dismissed" | "all";

function predictedOf(p: LoggedPrediction): string {
  const out = p.output as Record<string, unknown>;
  return p.kind === "compare" ? String(out.winner ?? "") : String(out.label ?? "");
}

export default function InboxTab() {
  const { id, detail, version, reload, reloadExamples, goTo } = useIntuition();
  const [status, setStatus] = useState<Status>("unreviewed");
  const [items, setItems] = useState<LoggedPrediction[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      setItems(await imPredictions(id, status));
      setError(null);
    } catch (e) {
      setError(errorMessage(e));
    }
  }, [id, status]);

  useEffect(() => {
    void load();
  }, [load]);

  async function act(p: LoggedPrediction, body: { label?: string; dismiss?: boolean }) {
    const index = items?.indexOf(p) ?? -1;
    setItems((list) => list?.filter((x) => x.id !== p.id) ?? null);
    try {
      await imReview(id, p.id, body);
      if (body.dismiss) toast("Dismissed");
      else toast.success(`Added to examples as “${labelText(body.label!, p.kind === "compare" ? "pair" : "item")}”`);
      void reload();
      if (!body.dismiss) void reloadExamples();
      if (status === "all") void load();
    } catch (e) {
      toast.error(errorMessage(e));
      setItems((list) => {
        if (!list) return list;
        const next = [...list];
        next.splice(Math.max(0, Math.min(index, next.length)), 0, p);
        return next;
      });
    }
  }

  const labels = version?.labels ?? [];
  const outputType = detail.model.output_type;

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <p className="m-0 max-w-2xl text-[12.5px] leading-relaxed text-muted-foreground">
          Predictions served to agents and the API. Reviewing one adds it to your examples. Least confident first.
        </p>
        <Segmented
          ariaLabel="Status"
          value={status}
          onChange={(s) => {
            setStatus(s);
            setItems(null);
          }}
          options={[
            { value: "unreviewed", label: `To review${detail.counts.inbox ? ` · ${detail.counts.inbox}` : ""}` },
            { value: "labeled", label: "Labeled" },
            { value: "dismissed", label: "Dismissed" },
            { value: "all", label: "All" },
          ]}
        />
      </div>

      {error !== null ? (
        <LoadError what="predictions" message={error} onRetry={() => void load()} />
      ) : items === null ? (
        <RmListSkeleton />
      ) : items.length === 0 ? (
        <EmptyState title={status === "unreviewed" ? "Inbox zero" : "Nothing here"}>
          {status === "unreviewed" ? (
            <>
              New predictions from agents land here. Try one in the{" "}
              <button type="button" className="underline underline-offset-2 hover:text-foreground" onClick={() => goTo("playground")}>
                Playground
              </button>{" "}
              or call the API.
            </>
          ) : (
            "No predictions with this status."
          )}
        </EmptyState>
      ) : (
        <ul className="m-0 list-none space-y-2.5 p-0">
          {items.map((p) => {
            const kind = p.kind === "compare" ? "pair" : "item";
            const predicted = predictedOf(p);
            const options = allowedLabels(outputType, kind, labels);
            return (
              <li key={p.id} className="rounded-lg border border-border bg-background">
                <div className="flex flex-wrap items-center gap-x-3 gap-y-1 border-b border-border-subtle px-4 py-2 text-[11.5px] text-muted-foreground">
                  <span className="inline-flex items-center gap-1.5">
                    Predicted <LabelTag label={labelText(predicted, kind)} tone="brand" />
                  </span>
                  <span>
                    <span className={cn("font-mono", (p.confidence ?? 1) < 0.6 ? "text-yellow-700 dark:text-yellow-400" : "text-foreground")}>{pct(p.confidence)}</span> confident
                  </span>
                  <span className="font-mono">{p.caller}</span>
                  <span className="font-mono">v{p.version}</span>
                  <span>{relativeTime(p.created_at)}</span>
                  <span className="flex-1" />
                  {p.status !== "unreviewed" && <LabelTag label={p.status} tone={p.status === "labeled" ? "success" : "muted"} />}
                  {p.example_id && (
                    <button type="button" className="underline underline-offset-2 hover:text-foreground" onClick={() => goTo("examples", { example: p.example_id! })}>
                      View example
                    </button>
                  )}
                </div>
                <div className={cn("px-4 py-3", p.input.item_b != null && "grid gap-4 md:grid-cols-2")}>
                  {p.input.item_b != null ? (
                    <>
                      <Side tag="A" winner={predicted === "a"}>
                        <ItemView item={p.input.item} />
                      </Side>
                      <Side tag="B" winner={predicted === "b"}>
                        <ItemView item={p.input.item_b} />
                      </Side>
                    </>
                  ) : (
                    <ItemView item={p.input.item} />
                  )}
                </div>
                {p.status === "unreviewed" && (
                  <div className="flex flex-wrap items-center gap-1.5 border-t border-border-subtle px-4 py-2">
                    <span className="mr-1 text-[12px] text-dim">Correct label:</span>
                    {options.map((label) => (
                      <Button key={label} size="xs" variant={label === predicted ? "secondary" : "outline"} onClick={() => void act(p, { label })}>
                        {label === predicted && <Check />}
                        {labelText(label, kind)}
                      </Button>
                    ))}
                    <span className="flex-1" />
                    <Button size="xs" variant="ghost" onClick={() => void act(p, { dismiss: true })}>
                      <X /> Dismiss
                    </Button>
                  </div>
                )}
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}

function Side({ tag, winner, children }: { tag: string; winner: boolean; children: React.ReactNode }) {
  return (
    <div className="min-w-0">
      <div className="mb-1 flex items-center gap-1.5 text-[11px] font-medium text-dim">
        {tag}
        {winner && <span className="tag tag-brand">predicted winner</span>}
      </div>
      {children}
    </div>
  );
}
