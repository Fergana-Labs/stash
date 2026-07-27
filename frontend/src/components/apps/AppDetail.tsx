"use client";

import { useState } from "react";
import Link from "next/link";
import { ExternalLink, FileText, Plus, RefreshCw, X } from "lucide-react";

import { reenrichRow, setRowTopics } from "@/lib/api";
import type { MiniProgramManifest, TableRow } from "@/lib/types";

import TopicInput from "./TopicInput";
import { cellText, cellLabels, displayTimestamp, internalPath } from "./cells";

/** The row detail pane — the reason an app beats a spreadsheet. Topics are
 *  editable here because the model's guess is a starting point, not a verdict;
 *  everything else stays read-only so there's no mode to get stuck in. */
export default function AppDetail({
  row,
  slug,
  manifest,
  knownTopics,
  onClose,
  onChanged,
}: {
  row: TableRow;
  slug: string;
  manifest: MiniProgramManifest;
  knownTopics: string[];
  onClose: () => void;
  onChanged: () => Promise<void> | void;
}) {
  const [requeued, setRequeued] = useState(false);
  const [error, setError] = useState("");
  const [addingTopic, setAddingTopic] = useState(false);
  const [savingTopics, setSavingTopics] = useState(false);

  const { detail } = manifest;
  const title = cellText(row, detail.title) || "Untitled";
  const subtitle = cellText(row, detail.subtitle);
  const badge = cellText(row, detail.badge);
  const timestamp = displayTimestamp(cellText(row, detail.timestamp));
  const body = cellText(row, detail.body);
  const labels = cellLabels(row, detail.labels);
  const link = cellText(row, detail.link);
  const archived = internalPath(cellText(row, detail.content));

  const saveTopics = async (next: string[]) => {
    setSavingTopics(true);
    setError("");
    try {
      await setRowTopics(slug, row.id, next);
      setAddingTopic(false);
      await onChanged();
    } catch {
      setError("Couldn't save topics.");
    } finally {
      setSavingTopics(false);
    }
  };

  const handleReenrich = async () => {
    setError("");
    try {
      await reenrichRow(slug, row.id);
      setRequeued(true);
    } catch {
      setError("Couldn't queue a refresh. Try again.");
    }
  };

  return (
    <aside
      data-testid="app-detail"
      className="fixed inset-y-0 left-[74px] right-0 z-30 flex w-auto flex-col border-l border-border bg-base shadow-xl lg:static lg:z-auto lg:h-full lg:w-[340px] lg:shrink-0 lg:shadow-none"
    >
      <div className="flex items-start justify-between gap-2 border-b border-border px-4 py-3">
        <div className="min-w-0">
          <h2 className="text-[14px] font-semibold leading-snug text-foreground">{title}</h2>
          <div className="mt-1 flex flex-wrap items-center gap-1.5 text-[11px] text-dim">
            {badge && <span className="rounded bg-raised px-1.5 py-0.5">{badge}</span>}
            {subtitle && <span className="truncate">{subtitle}</span>}
            {timestamp && <span>· {timestamp}</span>}
          </div>
        </div>
        <button
          type="button"
          onClick={onClose}
          aria-label="Close details"
          className="cursor-pointer rounded p-2 text-muted-foreground hover:bg-raised hover:text-foreground"
        >
          <X className="h-4 w-4" />
        </button>
      </div>

      <div className="scroll-thin flex-1 space-y-4 overflow-y-auto px-4 py-4">
        <section>
          <h3 className="mb-1.5 text-[11px] font-semibold uppercase tracking-wide text-dim">
            Summary
          </h3>
          {body ? (
            <p className="text-[13px] leading-relaxed text-foreground">{body}</p>
          ) : (
            <p className="text-[13px] italic text-dim">
              Not summarised yet — this fills in shortly after saving.
            </p>
          )}
        </section>

        <section data-testid="topics-editor">
          <h3 className="mb-1.5 text-[11px] font-semibold uppercase tracking-wide text-dim">
            Topics
          </h3>
          <div className="flex flex-wrap items-center gap-1">
            {labels.map((label) => (
              <span
                key={label}
                className="inline-flex items-center gap-1 rounded-full bg-brand/10 py-0.5 pl-2 pr-1 text-[11px] font-medium text-brand"
              >
                {label}
                <button
                  type="button"
                  aria-label={`Remove ${label}`}
                  disabled={savingTopics}
                  onClick={() => saveTopics(labels.filter((l) => l !== label))}
                  className="cursor-pointer rounded-full p-0.5 hover:bg-brand/20"
                >
                  <X className="h-2.5 w-2.5" />
                </button>
              </span>
            ))}
            {!addingTopic && (
              <button
                type="button"
                onClick={() => setAddingTopic(true)}
                data-testid="add-topic"
                className="inline-flex cursor-pointer items-center gap-0.5 rounded-full border border-dashed border-border px-2 py-0.5 text-[11px] text-muted-foreground hover:border-brand hover:text-brand"
              >
                <Plus className="h-2.5 w-2.5" />
                Add
              </button>
            )}
          </div>
          {addingTopic && (
            <div className="mt-2">
              <TopicInput
                knownTopics={knownTopics.filter((t) => !labels.includes(t))}
                onSubmit={(topic) => saveTopics([...labels, topic])}
                onCancel={() => setAddingTopic(false)}
              />
            </div>
          )}
        </section>

        <section className="space-y-1.5">
          {archived && (
            <Link
              href={archived}
              className="flex items-center gap-2 rounded-lg border border-border px-3 py-2 text-[12.5px] text-foreground hover:bg-raised"
            >
              <FileText className="h-3.5 w-3.5 text-brand" />
              Open saved copy
            </Link>
          )}
          {link && (
            <a
              href={link}
              target="_blank"
              rel="noopener noreferrer"
              className="flex items-center gap-2 rounded-lg border border-border px-3 py-2 text-[12.5px] text-foreground hover:bg-raised"
            >
              <ExternalLink className="h-3.5 w-3.5 text-brand" />
              Open original
            </a>
          )}
          <button
            type="button"
            onClick={handleReenrich}
            disabled={requeued}
            className="flex w-full cursor-pointer items-center gap-2 rounded-lg border border-border px-3 py-2 text-[12.5px] text-foreground hover:bg-raised disabled:cursor-default disabled:text-dim"
          >
            <RefreshCw className={`h-3.5 w-3.5 text-brand ${requeued ? "animate-spin" : ""}`} />
            {requeued ? "Queued — refreshing shortly" : "Regenerate summary"}
          </button>
          {error && <p className="text-[11.5px] text-red-500">{error}</p>}
        </section>
      </div>
    </aside>
  );
}
