"use client";

import { useEffect, useMemo, useState } from "react";

import { createFolder } from "@/lib/api";
import {
  NotionPageSummary,
  importNotion,
  listNotionPages,
} from "@/lib/integrations";
import { NotionIcon } from "@/components/integrations/BrandIcons";

type Props = {
  workspaceId: string;
  folderId?: string | null;
  onDispatched?: (taskIds: string[]) => void;
  onClose: () => void;
};

export default function NotionImportDialog({
  workspaceId,
  folderId,
  onDispatched,
  onClose,
}: Props) {
  const [pages, setPages] = useState<NotionPageSummary[] | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [query, setQuery] = useState("");
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
  const [makeFolder, setMakeFolder] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setLoadError(null);
    listNotionPages()
      .then((p) => {
        if (!cancelled) setPages(p);
      })
      .catch((e) => {
        if (cancelled) return;
        const msg = e instanceof Error ? e.message : String(e);
        if (msg.toLowerCase().includes("not connected")) {
          setLoadError("Connect Notion in Settings → Integrations to see your pages.");
        } else {
          setLoadError(msg);
        }
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const filtered = useMemo(() => {
    if (!pages) return [];
    const q = query.trim().toLowerCase();
    if (!q) return pages;
    return pages.filter((p) => p.title.toLowerCase().includes(q));
  }, [pages, query]);

  function toggle(id: string) {
    setSelectedIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  async function startImport() {
    if (selectedIds.size === 0 || !pages) return;
    setError(null);
    setSubmitting(true);
    try {
      let importFolderId = folderId ?? undefined;
      if (makeFolder) {
        const today = new Date().toISOString().slice(0, 10);
        const folder = await createFolder(
          workspaceId,
          `Notion import — ${today}`,
          folderId ?? undefined,
        );
        importFolderId = folder.id;
      }
      const urls = pages.filter((p) => selectedIds.has(p.id)).map((p) => p.url);
      const { task_ids } = await importNotion(workspaceId, {
        urls,
        folder_id: importFolderId,
      });
      onDispatched?.(task_ids);
      onClose();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
      setSubmitting(false);
    }
  }

  return (
    <div
      role="dialog"
      aria-modal="true"
      className="fixed inset-0 z-[1000] flex items-center justify-center bg-black/45"
      onClick={onClose}
    >
      <div
        onClick={(e) => e.stopPropagation()}
        className="flex w-[min(640px,92vw)] max-h-[80vh] flex-col rounded-xl bg-surface shadow-[0_24px_48px_rgba(0,0,0,0.18)]"
      >
        <div className="flex items-start gap-3 border-b border-border px-6 py-4">
          <NotionIcon size={24} className="mt-0.5 text-foreground" />
          <div className="flex-1">
            <h2 className="text-[15px] font-semibold text-foreground">
              Import from Notion
            </h2>
            <p className="mt-0.5 text-[12.5px] text-muted">
              Pages you've shared with the integration appear below. Select one
              or more to convert to markdown pages.
            </p>
          </div>
          <button
            type="button"
            onClick={onClose}
            disabled={submitting}
            className="rounded-md p-1 text-muted hover:bg-raised hover:text-foreground"
            aria-label="Close"
          >
            ✕
          </button>
        </div>

        <div className="px-6 pt-4">
          <input
            type="search"
            placeholder="Search pages…"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            disabled={!pages || submitting}
            className="w-full rounded-md border border-border bg-base px-3 py-2 text-[13px] text-foreground placeholder:text-muted focus:border-brand focus:outline-none"
          />
        </div>

        <div className="min-h-0 flex-1 overflow-y-auto px-3 py-2">
          {loadError && (
            <div className="m-3 rounded-md bg-red-50 px-3 py-2 text-[13px] text-red-700">
              {loadError}
            </div>
          )}
          {!pages && !loadError && (
            <div className="flex h-32 items-center justify-center text-[13px] text-muted">
              Loading your Notion pages…
            </div>
          )}
          {pages && filtered.length === 0 && !loadError && (
            <div className="flex h-32 items-center justify-center px-6 text-center text-[13px] text-muted">
              {query
                ? `No pages match "${query}".`
                : "No pages found. In Notion, share the pages you want to import with this integration."}
            </div>
          )}
          {filtered.map((p) => {
            const isSelected = selectedIds.has(p.id);
            return (
              <button
                key={p.id}
                type="button"
                onClick={() => toggle(p.id)}
                disabled={submitting}
                className={`flex w-full items-center gap-3 rounded-md px-3 py-2 text-left transition ${
                  isSelected ? "bg-brand-50 ring-1 ring-brand" : "hover:bg-raised"
                }`}
              >
                <input
                  type="checkbox"
                  checked={isSelected}
                  readOnly
                  className="h-4 w-4"
                  style={{ accentColor: "var(--color-brand)" }}
                />
                <span className="text-base">{p.icon || "📄"}</span>
                <div className="min-w-0 flex-1">
                  <div className="truncate text-[13px] font-medium text-foreground">
                    {p.title}
                  </div>
                  {p.last_edited_time && (
                    <div className="text-[11.5px] text-muted">
                      Edited{" "}
                      {new Date(p.last_edited_time).toLocaleDateString(undefined, {
                        month: "short",
                        day: "numeric",
                        year: "numeric",
                      })}
                    </div>
                  )}
                </div>
              </button>
            );
          })}
        </div>

        <div className="border-t border-border px-6 py-3">
          {error && (
            <div className="mb-2 rounded-md bg-red-50 px-3 py-2 text-[12.5px] text-red-700">
              {error}
            </div>
          )}
          <label className="mb-3 flex cursor-pointer items-center gap-2 text-[12.5px] text-foreground">
            <input
              type="checkbox"
              checked={makeFolder}
              onChange={(e) => setMakeFolder(e.target.checked)}
              disabled={submitting}
              className="h-3.5 w-3.5"
              style={{ accentColor: "var(--color-brand)" }}
            />
            <span>
              Put inside a new folder{" "}
              <span className="text-muted">named</span>{" "}
              <span className="font-mono text-muted">
                Notion import — {new Date().toISOString().slice(0, 10)}
              </span>
            </span>
          </label>
          <div className="flex items-center justify-between gap-2">
            <span className="text-[12px] text-muted">
              {selectedIds.size === 0
                ? "Select one or more pages"
                : `${selectedIds.size} selected`}
            </span>
            <div className="flex gap-2">
              <button
                type="button"
                onClick={onClose}
                disabled={submitting}
                className="rounded-md border border-border bg-base px-3 py-1.5 text-[12.5px] font-medium text-foreground hover:bg-raised disabled:cursor-wait disabled:opacity-60"
              >
                Cancel
              </button>
              <button
                type="button"
                onClick={startImport}
                disabled={selectedIds.size === 0 || submitting}
                className="rounded-md bg-brand px-3 py-1.5 text-[12.5px] font-medium text-white hover:bg-brand-hover disabled:cursor-not-allowed disabled:opacity-50"
              >
                {submitting
                  ? "Starting…"
                  : selectedIds.size > 1
                    ? `Import ${selectedIds.size} pages`
                    : "Import"}
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
