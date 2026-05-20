"use client";

import { useEffect, useMemo, useState } from "react";

import { createFolder } from "@/lib/api";
import {
  GitHubRepoSummary,
  importGitRepo,
  listGitHubRepos,
} from "@/lib/integrations";
import { GitHubIcon } from "@/components/integrations/BrandIcons";

type Props = {
  workspaceId: string;
  folderId?: string | null;
  /** Called as soon as the task is dispatched, with the task id. */
  onDispatched?: (taskIds: string[]) => void;
  onClose: () => void;
};

export default function GitImportDialog({
  workspaceId,
  folderId,
  onDispatched,
  onClose,
}: Props) {
  const [repos, setRepos] = useState<GitHubRepoSummary[] | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [query, setQuery] = useState("");
  const [selected, setSelected] = useState<GitHubRepoSummary | null>(null);
  const [makeFolder, setMakeFolder] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setLoadError(null);
    listGitHubRepos()
      .then((r) => {
        if (!cancelled) setRepos(r);
      })
      .catch((e) => {
        if (cancelled) return;
        const msg = e instanceof Error ? e.message : String(e);
        if (msg.toLowerCase().includes("not connected")) {
          setLoadError("Connect GitHub in Settings → Integrations to see your repos.");
        } else {
          setLoadError(msg);
        }
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const filtered = useMemo(() => {
    if (!repos) return [];
    const q = query.trim().toLowerCase();
    if (!q) return repos;
    return repos.filter(
      (r) =>
        r.full_name.toLowerCase().includes(q) ||
        (r.description || "").toLowerCase().includes(q),
    );
  }, [repos, query]);

  async function startImport() {
    if (!selected) return;
    setError(null);
    setSubmitting(true);
    try {
      let importFolderId = folderId ?? undefined;
      if (makeFolder) {
        const repoLeaf = selected.full_name.split("/").pop() || selected.full_name;
        const folder = await createFolder(workspaceId, repoLeaf, folderId ?? undefined);
        importFolderId = folder.id;
      }
      const { task_id } = await importGitRepo(workspaceId, {
        url: selected.html_url,
        folder_id: importFolderId,
      });
      onDispatched?.([task_id]);
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
          <GitHubIcon size={24} className="mt-0.5 text-foreground" />
          <div className="flex-1">
            <h2 className="text-[15px] font-semibold text-foreground">
              Import from GitHub
            </h2>
            <p className="mt-0.5 text-[12.5px] text-muted">
              Pick a repo to import. Markdown files become pages; everything
              else lands in Files with text extraction queued automatically.
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
            placeholder="Search your repositories…"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            disabled={!repos || submitting}
            className="w-full rounded-md border border-border bg-base px-3 py-2 text-[13px] text-foreground placeholder:text-muted focus:border-brand focus:outline-none"
          />
        </div>

        <div className="min-h-0 flex-1 overflow-y-auto px-3 py-2">
          {loadError && (
            <div className="m-3 rounded-md bg-red-50 px-3 py-2 text-[13px] text-red-700">
              {loadError}
            </div>
          )}
          {!repos && !loadError && (
            <div className="flex h-32 items-center justify-center text-[13px] text-muted">
              Loading your repositories…
            </div>
          )}
          {repos && filtered.length === 0 && !loadError && (
            <div className="flex h-32 items-center justify-center text-[13px] text-muted">
              No repos match &ldquo;{query}&rdquo;.
            </div>
          )}
          {filtered.map((r) => {
            const isSelected = selected?.full_name === r.full_name;
            return (
              <button
                key={r.full_name}
                type="button"
                onClick={() => setSelected(r)}
                disabled={submitting}
                className={`flex w-full items-start gap-3 rounded-md px-3 py-2 text-left transition ${
                  isSelected ? "bg-brand-50 ring-1 ring-brand" : "hover:bg-raised"
                }`}
              >
                <GitHubIcon size={16} className="mt-1 text-muted" />
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-2">
                    <span className="truncate text-[13px] font-medium text-foreground">
                      {r.full_name}
                    </span>
                    {r.private && (
                      <span className="rounded bg-raised px-1.5 py-0.5 text-[10px] uppercase tracking-wide text-muted">
                        Private
                      </span>
                    )}
                  </div>
                  {r.description && (
                    <div className="truncate text-[12px] text-muted">{r.description}</div>
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
              Put inside a new folder
              {selected ? (
                <span className="text-muted">
                  {" "}
                  named{" "}
                  <span className="font-mono">
                    {selected.full_name.split("/").pop()}
                  </span>
                </span>
              ) : null}
            </span>
          </label>
          <div className="flex items-center justify-between gap-2">
            <span className="text-[12px] text-muted">
              {selected ? selected.full_name : "Select a repo to continue"}
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
                disabled={!selected || submitting}
                className="rounded-md bg-brand px-3 py-1.5 text-[12.5px] font-medium text-white hover:bg-brand-hover disabled:cursor-not-allowed disabled:opacity-50"
              >
                {submitting ? "Starting…" : "Import"}
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
