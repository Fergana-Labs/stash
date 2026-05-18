"use client";

import { useEffect, useMemo, useState } from "react";
import {
  ApiError,
  addExternalStash,
  listAllPages,
  listAllTables,
  listFiles,
  listMySessions,
  updateStash,
  type StashItemSpec,
  type UserPageEntry,
  type SessionSummary,
  type WorkspaceFile,
} from "../../lib/api";
import type { TableWithWorkspace } from "../../lib/types";
import { stashSlugFromInput } from "../../lib/stashLinks";
import { useEscapeKey } from "../../hooks/useEscapeKey";

interface Props {
  open: boolean;
  onClose: () => void;
  /** The stash we're adding to. We mutate its items via updateStash. */
  stashId: string;
  /** The owning workspace — picker is scoped here. */
  workspaceId: string;
  /** Already-included items so we can grey them out / skip them. */
  existingItems: StashItemSpec[];
  /** Called after a successful add so the parent refetches. */
  onAdded: () => void;
}

type Tab = "workspace" | "external";

type PickerKind = "page" | "session" | "table" | "file";

interface PickerRow {
  kind: PickerKind;
  /** Stable composite key for React. */
  key: string;
  /** Display label. */
  label: string;
  /** Subtitle (folder path, timestamp, etc.). */
  sub: string;
  /** What we send when we add it to the stash. */
  spec: StashItemSpec;
}

export default function AddToStashModal({
  open,
  onClose,
  stashId,
  workspaceId,
  existingItems,
  onAdded,
}: Props) {
  const [tab, setTab] = useState<Tab>("workspace");
  const [query, setQuery] = useState("");
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Workspace tab data
  const [pages, setPages] = useState<UserPageEntry[]>([]);
  const [sessions, setSessions] = useState<SessionSummary[]>([]);
  const [tables, setTables] = useState<TableWithWorkspace[]>([]);
  const [files, setFiles] = useState<WorkspaceFile[]>([]);
  const [loading, setLoading] = useState(false);

  // External tab data
  const [externalUrl, setExternalUrl] = useState("");

  useEscapeKey(open, onClose);

  useEffect(() => {
    if (!open) return;
    setSelected(new Set());
    setError(null);
    setQuery("");
    setTab("workspace");
    setLoading(true);
    Promise.all([
      listAllPages().then((d) => d.pages.filter((p) => p.workspace_id === workspaceId)),
      listMySessions(workspaceId, 200),
      listAllTables().then((d) => d.tables.filter((t) => t.workspace_id === workspaceId)),
      listFiles(workspaceId),
    ])
      .then(([p, s, t, f]) => {
        setPages(p);
        setSessions(s);
        setTables(t);
        setFiles(f as WorkspaceFile[]);
      })
      .catch((e) => setError(e instanceof Error ? e.message : "Failed to load workspace items"))
      .finally(() => setLoading(false));
  }, [open, workspaceId]);

  const existingKeys = useMemo(
    () => new Set(existingItems.map((i) => `${i.object_type}:${i.object_id}`)),
    [existingItems]
  );

  const rows: PickerRow[] = useMemo(() => {
    const out: PickerRow[] = [];
    for (const p of pages) {
      out.push({
        kind: "page",
        key: `page:${p.id}`,
        label: p.name.replace(/\.md$/, ""),
        sub: p.folder_path.join(" / ") || "root",
        spec: { object_type: "page", object_id: p.id, position: 0 },
      });
    }
    for (const s of sessions) {
      out.push({
        kind: "session",
        key: `session:${s.session_id}`,
        label: s.first_prompt_preview?.slice(0, 80) || s.session_id,
        sub: `${s.agent_name || "agent"} · ${s.event_count} events`,
        spec: { object_type: "session", object_id: s.session_id, position: 0 },
      });
    }
    for (const t of tables) {
      const rc = t.row_count ?? 0;
      out.push({
        kind: "table",
        key: `table:${t.id}`,
        label: t.name,
        sub: `${rc} row${rc === 1 ? "" : "s"}`,
        spec: { object_type: "table", object_id: t.id, position: 0 },
      });
    }
    for (const f of files) {
      out.push({
        kind: "file",
        key: `file:${f.id}`,
        label: f.name,
        sub: `${f.content_type || "file"} · ${formatBytes(f.size_bytes)}`,
        spec: { object_type: "file", object_id: f.id, position: 0 },
      });
    }
    const q = query.trim().toLowerCase();
    if (!q) return out;
    return out.filter((r) => r.label.toLowerCase().includes(q) || r.sub.toLowerCase().includes(q));
  }, [pages, sessions, tables, files, query]);

  function toggle(key: string) {
    setSelected((s) => {
      const next = new Set(s);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });
  }

  async function saveWorkspaceSelection() {
    const toAdd = rows.filter((r) => selected.has(r.key)).map((r) => r.spec);
    if (toAdd.length === 0) {
      onClose();
      return;
    }
    setSubmitting(true);
    setError(null);
    try {
      // Backend's updateStash takes the full item set, so we union existing + new.
      const nextItems: StashItemSpec[] = [
        ...existingItems.map((it, i) => ({ ...it, position: i })),
        ...toAdd.map((it, i) => ({ ...it, position: existingItems.length + i })),
      ];
      await updateStash(stashId, { items: nextItems });
      onAdded();
      onClose();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Couldn't add items");
    } finally {
      setSubmitting(false);
    }
  }

  async function attachExternalStash() {
    const slug = stashSlugFromInput(externalUrl);
    if (!slug) {
      setError("Paste a stash URL or slug.");
      return;
    }
    setSubmitting(true);
    setError(null);
    try {
      await addExternalStash(workspaceId, slug);
      onAdded();
      onClose();
    } catch (e) {
      if (e instanceof ApiError && e.status === 404) {
        setError("Couldn't find that stash. Check the URL.");
      } else {
        setError(e instanceof Error ? e.message : "Couldn't attach external stash");
      }
    } finally {
      setSubmitting(false);
    }
  }

  if (!open) return null;

  return (
    <div
      onClick={onClose}
      className="fixed inset-0 z-50 flex items-start justify-center bg-black/30 p-6"
    >
      <div
        onClick={(e) => e.stopPropagation()}
        className="mt-20 flex w-full max-w-[640px] flex-col overflow-hidden rounded-xl border border-border bg-base shadow-xl"
      >
        <div className="flex items-center justify-between border-b border-border px-4 py-3">
          <h2 className="m-0 font-display text-[17px] font-semibold">Add to Stash</h2>
          <button
            type="button"
            onClick={onClose}
            className="rounded p-1 text-muted hover:bg-raised hover:text-foreground"
            aria-label="Close"
          >
            <CloseGlyph />
          </button>
        </div>

        {/* Tab strip */}
        <div className="flex gap-0.5 border-b border-border bg-surface px-2 pt-2">
          <TabBtn label="From workspace" active={tab === "workspace"} onClick={() => setTab("workspace")} />
          <TabBtn label="External Stash" active={tab === "external"} onClick={() => setTab("external")} />
        </div>

        {tab === "workspace" ? (
          <>
            <div className="border-b border-border px-4 py-2.5">
              <input
                type="text"
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                placeholder="Filter pages, sessions, tables, files…"
                className="w-full rounded-md border border-border bg-surface px-2.5 py-1.5 text-[13px] text-foreground placeholder:text-muted focus:border-[var(--color-brand-400)] focus:outline-none"
              />
            </div>
            <div className="scroll-thin max-h-[420px] overflow-y-auto px-2 py-2">
              {loading ? (
                <div className="px-2 py-6 text-center text-[12.5px] text-muted">Loading…</div>
              ) : rows.length === 0 ? (
                <div className="px-2 py-6 text-center text-[12.5px] text-muted">
                  {query.trim() ? "Nothing matches." : "No items in this workspace yet."}
                </div>
              ) : (
                rows.map((row) => {
                  const alreadyIn = existingKeys.has(row.key);
                  const checked = selected.has(row.key);
                  return (
                    <button
                      key={row.key}
                      type="button"
                      disabled={alreadyIn}
                      onClick={() => toggle(row.key)}
                      className={
                        "flex w-full items-center gap-2.5 rounded-md px-2 py-1.5 text-left " +
                        (alreadyIn
                          ? "cursor-default opacity-50"
                          : checked
                            ? "bg-[var(--color-brand-50)]"
                            : "hover:bg-raised")
                      }
                    >
                      <span className="flex h-4 w-4 flex-shrink-0 items-center justify-center rounded border border-border bg-base text-[10px] text-[var(--color-brand-700)]">
                        {checked || alreadyIn ? "✓" : ""}
                      </span>
                      <span className="font-mono text-[10px] uppercase tracking-wide text-muted">
                        {row.kind}
                      </span>
                      <span className="min-w-0 flex-1 truncate text-[13px] text-foreground">
                        {row.label}
                      </span>
                      <span className="hidden truncate text-[11.5px] text-muted sm:inline">
                        {alreadyIn ? "already in" : row.sub}
                      </span>
                    </button>
                  );
                })
              )}
            </div>
          </>
        ) : (
          <div className="px-4 py-4">
            <p className="m-0 text-[12.5px] text-muted">
              Paste a public Stash URL or slug. We&apos;ll fork its items into a new Stash inside
              this workspace and link it as an external Stash.
            </p>
            <input
              type="text"
              value={externalUrl}
              onChange={(e) => setExternalUrl(e.target.value)}
              placeholder="https://app.joinstash.ai/stashes/example-slug"
              className="mt-3 w-full rounded-md border border-border bg-surface px-2.5 py-1.5 text-[13px] text-foreground placeholder:text-muted focus:border-[var(--color-brand-400)] focus:outline-none"
            />
          </div>
        )}

        {error && (
          <div className="border-t border-red-200 bg-red-50 px-4 py-2 text-[12px] text-red-700">
            {error}
          </div>
        )}

        <div className="flex items-center justify-between gap-2 border-t border-border px-4 py-3">
          <span className="text-[11.5px] text-muted">
            {tab === "workspace"
              ? `${selected.size} selected`
              : "Forks a copy into this workspace."}
          </span>
          <div className="flex gap-1.5">
            <button
              type="button"
              onClick={onClose}
              className="rounded-md border border-border bg-base px-3 py-1.5 text-[12.5px] text-foreground hover:bg-raised"
            >
              Cancel
            </button>
            <button
              type="button"
              disabled={submitting}
              onClick={tab === "workspace" ? saveWorkspaceSelection : attachExternalStash}
              className="rounded-md bg-[var(--color-brand-600)] px-3 py-1.5 text-[12.5px] font-medium text-white hover:bg-[var(--color-brand-700)] disabled:opacity-50"
            >
              {submitting ? "Adding…" : tab === "workspace" ? "Add" : "Fork into workspace"}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

function TabBtn({ label, active, onClick }: { label: string; active: boolean; onClick: () => void }) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={
        "rounded-t-md px-3 py-1.5 text-[12.5px] " +
        (active
          ? "bg-base font-semibold text-foreground"
          : "text-muted hover:text-foreground")
      }
    >
      {label}
    </button>
  );
}

function CloseGlyph() {
  return (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
      <path d="M18 6L6 18M6 6l12 12" />
    </svg>
  );
}

function formatBytes(b: number): string {
  if (!b) return "0 B";
  if (b < 1024) return `${b} B`;
  if (b < 1024 * 1024) return `${(b / 1024).toFixed(1)} KB`;
  return `${(b / 1024 / 1024).toFixed(1)} MB`;
}
