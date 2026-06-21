"use client";

import { useRouter } from "next/navigation";
import { useCallback, useEffect, useMemo, useState } from "react";
import { useBreadcrumbs } from "@/components/BreadcrumbContext";
import { useConfirm } from "@/components/ConfirmDialog";
import { useAuth } from "@/hooks/useAuth";
import { getTrash, purgeItem, restoreItem } from "@/lib/api";
import type { TrashEntry, TrashKind, TrashListing } from "@/lib/types";

type RowKind = TrashKind;

const SECTION_TITLES: Record<RowKind, string> = {
  page: "Pages",
  file: "Files",
  session: "Sessions",
};

// Selection keys are kind-namespaced because page + file UUIDs can collide
// in trash listings.
function key(kind: RowKind, id: string) {
  return `${kind}:${id}`;
}

export default function TrashPage() {
  const router = useRouter();
  const { user, loading } = useAuth();
  const confirm = useConfirm();

  const [data, setData] = useState<TrashListing | null>(null);
  const [error, setError] = useState("");
  const [busyId, setBusyId] = useState<string | null>(null);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [bulkBusy, setBulkBusy] = useState(false);

  useBreadcrumbs([{ label: "Trash" }], "trash");

  const load = useCallback(async () => {
    try {
      setData(await getTrash());
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load trash");
    }
  }, []);

  useEffect(() => {
    if (user) load();
  }, [user, load]);

  useEffect(() => {
    if (!loading && !user) router.push("/login");
  }, [user, loading, router]);

  // Drop stale selections when the trash listing changes (item restored
  // by someone else, list refreshed, etc.).
  useEffect(() => {
    if (!data) return;
    const live = new Set<string>();
    for (const k of ["page", "file", "session"] as const) {
      for (const e of data[`${k}s`]) live.add(key(k, e.id));
    }
    setSelected((cur) => {
      const next = new Set<string>();
      cur.forEach((k) => {
        if (live.has(k)) next.add(k);
      });
      return next.size === cur.size ? cur : next;
    });
  }, [data]);

  function toggleOne(kind: RowKind, id: string) {
    setSelected((cur) => {
      const next = new Set(cur);
      const k = key(kind, id);
      if (next.has(k)) next.delete(k);
      else next.add(k);
      return next;
    });
  }

  function toggleSection(kind: RowKind, entries: TrashEntry[]) {
    const ids = entries.map((e) => key(kind, e.id));
    setSelected((cur) => {
      const next = new Set(cur);
      const allSelected = ids.every((k) => next.has(k));
      if (allSelected) ids.forEach((k) => next.delete(k));
      else ids.forEach((k) => next.add(k));
      return next;
    });
  }

  function toggleAll(all: { kind: RowKind; id: string }[]) {
    setSelected((cur) => {
      if (cur.size === all.length) return new Set();
      return new Set(all.map((x) => key(x.kind, x.id)));
    });
  }

  async function handleRestore(kind: RowKind, id: string) {
    setBusyId(id);
    setError("");
    try {
      await restoreItem(kind, id);
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Restore failed");
    } finally {
      setBusyId(null);
    }
  }

  async function handlePurge(kind: RowKind, id: string, name: string) {
    const ok = await confirm({
      title: `Permanently delete "${name}"?`,
      body: "This cannot be undone.",
      confirmLabel: "Delete",
    });
    if (!ok) return;
    setBusyId(id);
    setError("");
    try {
      await purgeItem(kind, id);
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Permanent delete failed");
    } finally {
      setBusyId(null);
    }
  }

  // Parse each "kind:id" selection back into a typed call. Bulk ops are
  // a simple Promise.all — if anything fails we surface the first error
  // and reload to show the consistent post-operation state.
  function parseSelection(): { kind: RowKind; id: string }[] {
    const out: { kind: RowKind; id: string }[] = [];
    selected.forEach((k) => {
      const [kind, id] = k.split(":") as [RowKind, string];
      if (kind === "page" || kind === "file" || kind === "session") {
        out.push({ kind, id });
      }
    });
    return out;
  }

  async function handleBulkRestore() {
    const items = parseSelection();
    if (items.length === 0) return;
    setBulkBusy(true);
    setError("");
    try {
      await Promise.all(items.map((it) => restoreItem(it.kind, it.id)));
      setSelected(new Set());
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Bulk restore failed");
      await load();
    } finally {
      setBulkBusy(false);
    }
  }

  async function handleBulkPurge() {
    const items = parseSelection();
    if (items.length === 0) return;
    const ok = await confirm({
      title: `Permanently delete ${items.length} item${items.length === 1 ? "" : "s"}?`,
      body: "This cannot be undone.",
      confirmLabel: "Delete",
    });
    if (!ok) return;
    setBulkBusy(true);
    setError("");
    try {
      await Promise.all(items.map((it) => purgeItem(it.kind, it.id)));
      setSelected(new Set());
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Bulk delete failed");
      await load();
    } finally {
      setBulkBusy(false);
    }
  }

  const allItems = useMemo(() => {
    if (!data) return [];
    return [
      ...data.pages.map((e) => ({ kind: "page" as const, id: e.id })),
      ...data.files.map((e) => ({ kind: "file" as const, id: e.id })),
      ...data.sessions.map((e) => ({ kind: "session" as const, id: e.id })),
    ];
  }, [data]);

  if (loading || !data)
    return <div className="flex h-screen items-center justify-center text-muted">Loading…</div>;
  if (!user) return null;

  const total = allItems.length;
  const allChecked = total > 0 && selected.size === total;
  const someChecked = selected.size > 0 && !allChecked;

  return (
    <div className="scroll-thin flex-1 overflow-y-auto">
      <div className="mx-auto max-w-5xl px-12 py-8">
        <div className="flex items-baseline justify-between gap-4">
          <h1 className="font-display text-[28px] font-bold tracking-tight text-foreground">
            Trash
          </h1>
          <span className="sys-label" style={{ fontSize: 10.5 }}>
            {total} item{total === 1 ? "" : "s"}
          </span>
        </div>

        <p className="mt-2 text-[13px] text-muted">
          Items here are recoverable. Permanent delete cannot be undone.
        </p>

        {error && (
          <div className="mt-4 rounded-lg border border-red-300/40 bg-red-500/10 px-4 py-2 text-[13px] text-red-500">
            {error}
          </div>
        )}

        {total > 0 && (
          <div className="mt-6 flex items-center gap-3 rounded-lg border border-border bg-surface px-4 py-2.5 text-[13px]">
            <label className="inline-flex cursor-pointer items-center gap-2 text-foreground">
              <input
                ref={(el) => {
                  if (el) el.indeterminate = someChecked;
                }}
                type="checkbox"
                checked={allChecked}
                onChange={() => toggleAll(allItems)}
                className="h-4 w-4 rounded border-border accent-[var(--color-brand-600)]"
                aria-label="Select all trashed items"
              />
              <span className="text-muted">
                {selected.size === 0
                  ? "Select all"
                  : `${selected.size} of ${total} selected`}
              </span>
            </label>
            <span className="flex-1" />
            <button
              type="button"
              disabled={bulkBusy || selected.size === 0}
              onClick={handleBulkRestore}
              className="cursor-pointer rounded-md border border-border bg-base px-3 py-1 text-[12px] text-foreground hover:bg-raised disabled:opacity-50"
            >
              Restore {selected.size > 0 ? `(${selected.size})` : ""}
            </button>
            <button
              type="button"
              disabled={bulkBusy || selected.size === 0}
              onClick={handleBulkPurge}
              className="cursor-pointer rounded-md border border-red-300/60 bg-red-500/5 px-3 py-1 text-[12px] text-red-600 hover:bg-red-500/10 disabled:opacity-50"
            >
              Delete forever {selected.size > 0 ? `(${selected.size})` : ""}
            </button>
          </div>
        )}

        <div className="mt-4 flex flex-col gap-6">
          {(["page", "file", "session"] as const).map((kind) => (
            <TrashSection
              key={kind}
              title={SECTION_TITLES[kind]}
              kind={kind}
              entries={data[`${kind}s`]}
              busyId={busyId}
              bulkBusy={bulkBusy}
              selected={selected}
              onToggle={toggleOne}
              onToggleSection={toggleSection}
              onRestore={handleRestore}
              onPurge={handlePurge}
            />
          ))}
          {total === 0 && (
            <div className="rounded-lg border border-dashed border-border bg-surface/30 px-4 py-8 text-center text-[12.5px] text-muted">
              Nothing in trash.
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

function TrashSection({
  title,
  kind,
  entries,
  busyId,
  bulkBusy,
  selected,
  onToggle,
  onToggleSection,
  onRestore,
  onPurge,
}: {
  title: string;
  kind: RowKind;
  entries: TrashEntry[];
  busyId: string | null;
  bulkBusy: boolean;
  selected: Set<string>;
  onToggle: (kind: RowKind, id: string) => void;
  onToggleSection: (kind: RowKind, entries: TrashEntry[]) => void;
  onRestore: (kind: RowKind, id: string) => void;
  onPurge: (kind: RowKind, id: string, name: string) => void;
}) {
  if (entries.length === 0) return null;
  const sectionSelected = entries.filter((e) => selected.has(key(kind, e.id))).length;
  const allSel = sectionSelected === entries.length;
  const someSel = sectionSelected > 0 && !allSel;
  return (
    <section>
      <h2 className="mb-2 flex items-center gap-2 font-display text-[15px] font-semibold text-foreground">
        <input
          ref={(el) => {
            if (el) el.indeterminate = someSel;
          }}
          type="checkbox"
          checked={allSel}
          onChange={() => onToggleSection(kind, entries)}
          className="h-4 w-4 rounded border-border accent-[var(--color-brand-600)]"
          aria-label={`Select all ${title.toLowerCase()}`}
        />
        {title} <span className="text-muted">({entries.length})</span>
      </h2>
      <div className="overflow-hidden rounded-lg border border-border bg-surface">
        {entries.map((entry) => {
          const isSel = selected.has(key(kind, entry.id));
          return (
            <div
              key={entry.id}
              className={
                "flex items-center gap-3 border-b border-border px-4 py-2.5 text-[13px] last:border-b-0 " +
                (isSel ? "bg-[var(--color-brand-50)]/40" : "")
              }
            >
              <input
                type="checkbox"
                checked={isSel}
                onChange={() => onToggle(kind, entry.id)}
                className="h-4 w-4 rounded border-border accent-[var(--color-brand-600)]"
                aria-label={`Select ${entry.name}`}
              />
              <div className="min-w-0 flex-1">
                <div className="truncate font-medium text-foreground">{entry.name}</div>
                <div className="mt-0.5 truncate text-[11.5px] text-muted">
                  Deleted {formatRelative(entry.deleted_at)}
                  {entry.deleted_by_name ? ` by ${entry.deleted_by_name}` : ""}
                </div>
              </div>
              <button
                type="button"
                disabled={busyId === entry.id || bulkBusy}
                onClick={() => onRestore(kind, entry.id)}
                className="cursor-pointer rounded-md border border-border bg-base px-3 py-1 text-[12px] text-foreground hover:bg-raised disabled:opacity-50"
              >
                Restore
              </button>
              <button
                type="button"
                disabled={busyId === entry.id || bulkBusy}
                onClick={() => onPurge(kind, entry.id, entry.name)}
                className="cursor-pointer rounded-md border border-red-300/60 bg-red-500/5 px-3 py-1 text-[12px] text-red-600 hover:bg-red-500/10 disabled:opacity-50"
              >
                Delete forever
              </button>
            </div>
          );
        })}
      </div>
    </section>
  );
}

function formatRelative(iso: string | null): string {
  if (!iso) return "";
  const then = new Date(iso).getTime();
  if (Number.isNaN(then)) return "";
  const diffMs = Date.now() - then;
  const diffMin = Math.round(diffMs / 60000);
  if (diffMin < 1) return "just now";
  if (diffMin < 60) return `${diffMin}m ago`;
  const diffH = Math.round(diffMin / 60);
  if (diffH < 24) return `${diffH}h ago`;
  const diffD = Math.round(diffH / 24);
  if (diffD < 7) return `${diffD}d ago`;
  return new Date(iso).toLocaleDateString();
}
