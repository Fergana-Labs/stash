"use client";

import { useState } from "react";
import { Loader2, Tag, Trash2, X } from "lucide-react";

import { bulkEditRows } from "@/lib/api";

import TopicInput from "./TopicInput";

/** Actions on a selection. Appears only when something is selected, so the
 *  normal browsing view carries no extra chrome. */
export default function AppBulkBar({
  slug,
  selectedIds,
  knownTopics,
  onClear,
  onDone,
}: {
  slug: string;
  selectedIds: string[];
  knownTopics: string[];
  onClear: () => void;
  onDone: () => Promise<void> | void;
}) {
  const [busy, setBusy] = useState(false);
  const [tagging, setTagging] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [error, setError] = useState("");

  const run = async (body: Parameters<typeof bulkEditRows>[1]) => {
    setBusy(true);
    setError("");
    try {
      await bulkEditRows(slug, body);
      setTagging(false);
      setConfirmDelete(false);
      await onDone();
    } catch {
      setError("That didn't go through.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div
      data-testid="bulk-bar"
      className="flex flex-wrap items-center gap-2 border-t border-border bg-surface px-6 py-3"
    >
      <span className="text-[12.5px] font-medium text-foreground">
        {selectedIds.length} selected
      </span>

      {tagging ? (
        <TopicInput
          knownTopics={knownTopics}
          placeholder="Add a topic to all selected…"
          onSubmit={(topic) => run({ row_ids: selectedIds, action: "add_topics", topics: [topic] })}
          onCancel={() => setTagging(false)}
        />
      ) : (
        <button
          type="button"
          onClick={() => setTagging(true)}
          disabled={busy}
          className="inline-flex cursor-pointer items-center gap-1.5 rounded-lg border border-border px-2.5 py-1.5 text-[12px] text-foreground hover:bg-raised"
        >
          <Tag className="h-3.5 w-3.5" />
          Add topic
        </button>
      )}

      {confirmDelete ? (
        <span className="inline-flex items-center gap-2 text-[12px] text-foreground">
          Delete {selectedIds.length}?
          <button
            type="button"
            onClick={() => run({ row_ids: selectedIds, action: "delete" })}
            disabled={busy}
            className="cursor-pointer rounded-lg bg-red-600 px-2.5 py-1.5 text-[12px] font-medium text-white hover:bg-red-700"
          >
            {busy ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : "Delete"}
          </button>
          <button
            type="button"
            onClick={() => setConfirmDelete(false)}
            className="cursor-pointer text-[12px] text-muted-foreground hover:text-foreground"
          >
            Cancel
          </button>
        </span>
      ) : (
        <button
          type="button"
          onClick={() => setConfirmDelete(true)}
          disabled={busy}
          className="inline-flex cursor-pointer items-center gap-1.5 rounded-lg border border-border px-2.5 py-1.5 text-[12px] text-red-600 hover:bg-red-500/10"
        >
          <Trash2 className="h-3.5 w-3.5" />
          Delete
        </button>
      )}

      {error && <span className="text-[11.5px] text-red-500">{error}</span>}

      <button
        type="button"
        onClick={onClear}
        className="ml-auto inline-flex cursor-pointer items-center gap-1 text-[12px] text-muted-foreground hover:text-foreground"
      >
        <X className="h-3.5 w-3.5" />
        Clear
      </button>
    </div>
  );
}
