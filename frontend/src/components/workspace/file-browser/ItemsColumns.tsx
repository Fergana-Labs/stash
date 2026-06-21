"use client";

import { useEffect, useMemo, useRef, useState, type DragEvent } from "react";
import { getFolderContents, type FolderContents } from "../../../lib/api";
import { useEscapeKey } from "../../../hooks/useEscapeKey";
import { shouldOpenInNewTab, type NavigateOptions } from "../../../lib/linkNavigation";
import { KindIcon, tintFor, typeFor, type GridItem } from "./kind";
import { FB_DRAG_MIME, type FBDragPayload } from "./WorkspaceFileBrowser";

interface Props {
  rootItems: GridItem[];
  onNavigate: (item: GridItem, options?: NavigateOptions) => void;
  onReparent: (payload: FBDragPayload, targetFolderId: string | null) => Promise<void>;
  onDelete?: (item: GridItem) => Promise<void>;
}

type SortKey = "name" | "date" | "type" | "size";
type Sort = { key: SortKey; dir: "asc" | "desc" };

const SORT_STORAGE_KEY = "stash_columns_sort";

const DEFAULT_SORT: Sort = { key: "name", dir: "asc" };

// Each key's natural first direction: names/types read A→Z, but dates and sizes
// are most useful largest/newest first.
const SORT_OPTIONS: { key: SortKey; label: string }[] = [
  { key: "name", label: "Name" },
  { key: "date", label: "Date created" },
  { key: "type", label: "Type" },
  { key: "size", label: "Size" },
];

function defaultDirFor(key: SortKey): "asc" | "desc" {
  return key === "date" || key === "size" ? "desc" : "asc";
}

function readSort(): Sort {
  if (typeof window === "undefined") return DEFAULT_SORT;
  const raw = window.localStorage.getItem(SORT_STORAGE_KEY);
  if (!raw) return DEFAULT_SORT;
  const [key, dir] = raw.split(":");
  const keyOk = key === "name" || key === "date" || key === "type" || key === "size";
  if (keyOk && (dir === "asc" || dir === "desc")) return { key, dir };
  return DEFAULT_SORT;
}

function timeOf(item: GridItem): number {
  if (!item.updatedAt) return 0;
  const t = new Date(item.updatedAt).getTime();
  return Number.isNaN(t) ? 0 : t;
}

// Ascending comparators; the caller reverses for descending. Every key falls
// back to name so equal values keep a stable, readable order.
function compareItems(a: GridItem, b: GridItem, key: SortKey): number {
  if (key === "date") return timeOf(a) - timeOf(b) || a.name.localeCompare(b.name);
  if (key === "type") return typeFor(a).localeCompare(typeFor(b)) || a.name.localeCompare(b.name);
  if (key === "size") return (a.sizeBytes ?? 0) - (b.sizeBytes ?? 0) || a.name.localeCompare(b.name);
  return a.name.localeCompare(b.name);
}

function sortItems(items: GridItem[], sort: Sort): GridItem[] {
  const arr = [...items].sort((a, b) => compareItems(a, b, sort.key));
  if (sort.dir === "desc") arr.reverse();
  return arr;
}

// Finder-style column view: a stack of identical folder columns that grow
// to the right as the user drills, plus a metadata-only preview panel for
// the rightmost selected leaf. Each column has the same shape and behavior;
// clicking a folder in column N opens its contents in column N+1, clicking
// a non-folder selects it for the preview.
export default function ItemsColumns({
  rootItems,
  onNavigate,
  onReparent,
  onDelete,
}: Props) {
  // path: folder IDs of the drill trail. Empty array = root only.
  const [path, setPath] = useState<string[]>([]);
  const [cache, setCache] = useState<Map<string, FolderContents | null>>(new Map());
  const [selected, setSelected] = useState<{ columnIdx: number; item: GridItem } | null>(
    null
  );
  const [sort, setSort] = useState<Sort>(() => readSort());
  const containerRef = useRef<HTMLDivElement | null>(null);

  function applySort(next: Sort) {
    try {
      window.localStorage.setItem(SORT_STORAGE_KEY, `${next.key}:${next.dir}`);
    } catch {
      /* ignore */
    }
    setSort(next);
  }

  // Picking the active key flips its direction; picking a new key starts from
  // that key's natural direction.
  function chooseSort(key: SortKey) {
    applySort(
      sort.key === key
        ? { key, dir: sort.dir === "asc" ? "desc" : "asc" }
        : { key, dir: defaultDirFor(key) }
    );
  }

  // Fetch any missing folder contents along the current path.
  useEffect(() => {
    let cancelled = false;
    async function ensure() {
      const missing = path.filter((id) => !cache.has(id));
      if (missing.length === 0) return;
      const fetched = await Promise.all(
        missing.map(async (id) => [id, await getFolderContents(id)] as const)
      );
      if (cancelled) return;
      setCache((cur) => {
        const next = new Map(cur);
        for (const [id, contents] of fetched) next.set(id, contents);
        return next;
      });
    }
    void ensure();
    return () => {
      cancelled = true;
    };
  }, [path, cache]);

  // Keep the rightmost column visible as the user drills.
  useEffect(() => {
    const el = containerRef.current;
    if (el) el.scrollLeft = el.scrollWidth;
  }, [path]);

  function columnItemsAt(idx: number): GridItem[] {
    if (idx === 0) return sortItems(rootItems, sort);
    const folderId = path[idx - 1];
    const contents = cache.get(folderId);
    if (!contents) return [];
    return sortItems(folderContentsToItems(contents), sort);
  }

  function handlePick(columnIdx: number, item: GridItem) {
    if (item.kind === "folder") {
      // Drill into folder: truncate path at this column and append.
      setPath((cur) => [...cur.slice(0, columnIdx), item.id]);
      setSelected({ columnIdx, item });
      return;
    }
    // Leaf click: trim any deeper columns and surface in the preview panel.
    setPath((cur) => cur.slice(0, columnIdx));
    setSelected({ columnIdx, item });
  }

  function handleOpen(item: GridItem, options?: NavigateOptions) {
    if (item.kind === "folder" && !options?.newTab) return; // drilling handled above
    onNavigate(item, options);
  }

  // Build column data: root + one per element of path.
  const columns = useMemo(() => {
    const out: { idx: number; folderId: string | null; items: GridItem[] }[] = [
      { idx: 0, folderId: null, items: columnItemsAt(0) },
    ];
    for (let i = 0; i < path.length; i++) {
      out.push({ idx: i + 1, folderId: path[i], items: columnItemsAt(i + 1) });
    }
    return out;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [path, cache, rootItems, sort]);

  // The active id per column so each column highlights the drilled-into
  // folder (or the previewed leaf).
  function activeIdInColumn(columnIdx: number): string | null {
    if (columnIdx < path.length) return path[columnIdx];
    if (selected && selected.columnIdx === columnIdx) return selected.item.id;
    return null;
  }

  return (
    <div className="flex min-h-0 flex-1 flex-col overflow-hidden rounded-xl border border-border bg-surface">
      <div className="flex items-center justify-end border-b border-border bg-base/60 px-3 py-1.5">
        <SortMenu sort={sort} onChoose={chooseSort} />
      </div>
      <div className="flex min-h-0 flex-1 overflow-hidden">
        <div
          ref={containerRef}
          className="scroll-thin flex min-h-0 flex-1 overflow-x-auto"
        >
          {columns.map((col) => (
            <Column
              key={`${col.idx}-${col.folderId ?? "root"}`}
              items={col.items}
              activeId={activeIdInColumn(col.idx)}
              onPick={(item) => handlePick(col.idx, item)}
              onOpen={handleOpen}
              onReparent={onReparent}
              onDelete={onDelete}
              folderIdForDrop={col.folderId}
              loading={col.idx > 0 && !cache.get(col.folderId!) }
            />
          ))}
        </div>
        <PreviewPanel
          selected={selected?.item ?? null}
          onOpen={() => selected && handleOpen(selected.item)}
          onDelete={onDelete ? () => selected && onDelete(selected.item) : undefined}
        />
      </div>
    </div>
  );
}

// A single "Sort by" dropdown that applies to every column. Picking the active
// key flips its direction (arrow shows which way); picking another switches key.
function SortMenu({
  sort,
  onChoose,
}: {
  sort: Sort;
  onChoose: (key: SortKey) => void;
}) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  useEscapeKey(open, () => setOpen(false));

  useEffect(() => {
    if (!open) return;
    const onDown = (e: MouseEvent) => {
      if (!ref.current?.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", onDown);
    return () => {
      document.removeEventListener("mousedown", onDown);
    };
  }, [open]);

  const activeLabel = SORT_OPTIONS.find((o) => o.key === sort.key)?.label ?? "Name";
  const arrow = sort.dir === "desc" ? "▼" : "▲";

  return (
    <div ref={ref} className="relative">
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        aria-haspopup="listbox"
        aria-expanded={open}
        className="flex cursor-pointer items-center gap-1.5 rounded-md px-2 py-1 text-[12px] font-medium text-muted transition-colors hover:bg-raised hover:text-foreground"
      >
        Sort: {activeLabel}
        <span className="text-[9px]">{arrow}</span>
        <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
          <polyline points="6 9 12 15 18 9" />
        </svg>
      </button>
      {open && (
        <div className="absolute right-0 top-full z-30 mt-1 w-44 overflow-hidden rounded-md border border-border bg-surface py-1 text-[12.5px] shadow-lg">
          {SORT_OPTIONS.map((opt) => {
            const active = sort.key === opt.key;
            return (
              <button
                key={opt.key}
                type="button"
                onClick={() => {
                  onChoose(opt.key);
                  setOpen(false);
                }}
                className="flex w-full cursor-pointer items-center justify-between gap-2 px-3 py-1.5 text-left text-foreground hover:bg-raised"
              >
                <span className="truncate">{opt.label}</span>
                {active && <span className="text-[9px] text-muted">{arrow}</span>}
              </button>
            );
          })}
        </div>
      )}
    </div>
  );
}

function Column({
  items,
  activeId,
  onPick,
  onOpen,
  onReparent,
  onDelete,
  folderIdForDrop,
  loading,
}: {
  items: GridItem[];
  activeId: string | null;
  onPick: (item: GridItem) => void;
  onOpen: (item: GridItem, options?: NavigateOptions) => void;
  onReparent: (payload: FBDragPayload, targetFolderId: string | null) => Promise<void>;
  onDelete?: (item: GridItem) => Promise<void>;
  folderIdForDrop: string | null;
  loading: boolean;
}) {
  const [over, setOver] = useState(false);
  return (
    <div
      onDragOver={(e) => {
        if (!e.dataTransfer.types.includes(FB_DRAG_MIME)) return;
        e.preventDefault();
        e.dataTransfer.dropEffect = "move";
        setOver(true);
      }}
      onDragLeave={() => setOver(false)}
      onDrop={(e) => {
        const raw = e.dataTransfer.getData(FB_DRAG_MIME);
        setOver(false);
        if (!raw) return;
        e.preventDefault();
        try {
          const payload = JSON.parse(raw) as FBDragPayload;
          if (payload.kind === "folder" && payload.id === folderIdForDrop) return;
          onReparent(payload, folderIdForDrop);
        } catch {
          /* malformed */
        }
      }}
      className={
        // flex-[grow_shrink_basis]: each column starts at 240px, grows to fill
        // when the drill is shallow (so a single column doesn't float in empty
        // space), and never shrinks below 240px so deeper drills scroll instead.
        "scroll-thin flex h-full min-w-0 flex-[1_0_240px] flex-col overflow-y-auto border-r border-border bg-base " +
        (over ? "bg-[var(--color-brand-50)]/40" : "")
      }
    >
      {loading && (
        <div className="px-3 py-2 text-[12px] text-muted">Loading…</div>
      )}
      {!loading && items.length === 0 && (
        <div className="px-3 py-2 text-[12px] italic text-muted">Empty</div>
      )}
      {items.map((item) => (
        <ColumnRow
          key={`${item.kind}-${item.id}`}
          item={item}
          active={item.id === activeId}
          onPick={() => onPick(item)}
          onOpen={(options) => onOpen(item, options)}
          onReparent={onReparent}
          onDelete={onDelete}
        />
      ))}
    </div>
  );
}

function ColumnRow({
  item,
  active,
  onPick,
  onOpen,
  onReparent,
  onDelete,
}: {
  item: GridItem;
  active: boolean;
  onPick: () => void;
  onOpen: (options?: NavigateOptions) => void;
  onReparent: (payload: FBDragPayload, targetFolderId: string | null) => Promise<void>;
  onDelete?: (item: GridItem) => Promise<void>;
}) {
  const [over, setOver] = useState(false);
  const isFolder = item.kind === "folder";
  return (
    <div
      onClick={(e) => {
        if (shouldOpenInNewTab(e)) {
          onOpen({ newTab: true });
          return;
        }
        onPick();
      }}
      onAuxClick={(e) => {
        if (shouldOpenInNewTab(e)) onOpen({ newTab: true });
      }}
      onDoubleClick={() => onOpen()}
      role="button"
      tabIndex={0}
      onKeyDown={(e) => {
        if (e.key === "Enter") onOpen();
      }}
      draggable={item.movable !== false}
      onDragStart={(e: DragEvent<HTMLDivElement>) => {
        if (item.movable === false) {
          e.preventDefault();
          return;
        }
        const payload: FBDragPayload = { kind: item.kind, id: item.id };
        e.dataTransfer.setData(FB_DRAG_MIME, JSON.stringify(payload));
        e.dataTransfer.effectAllowed = "move";
      }}
      onDragOver={(e) => {
        if (!isFolder) return;
        if (!e.dataTransfer.types.includes(FB_DRAG_MIME)) return;
        e.preventDefault();
        e.dataTransfer.dropEffect = "move";
        setOver(true);
      }}
      onDragLeave={() => setOver(false)}
      onDrop={(e) => {
        if (!isFolder) return;
        const raw = e.dataTransfer.getData(FB_DRAG_MIME);
        setOver(false);
        if (!raw) return;
        e.preventDefault();
        try {
          const p = JSON.parse(raw) as FBDragPayload;
          if (p.kind === "folder" && p.id === item.id) return;
          onReparent(p, item.id);
        } catch {
          /* malformed */
        }
      }}
      className={
        "group flex cursor-pointer select-none items-center gap-2 px-3 py-1.5 text-[13px] " +
        (active
          ? "bg-[var(--color-brand-600)] text-white"
          : "text-foreground hover:bg-[var(--color-brand-50)]/50") +
        (over ? " ring-1 ring-inset ring-[var(--color-brand-300)]" : "")
      }
    >
      <span className={"flex h-4 w-4 flex-shrink-0 items-center justify-center " + (active ? "" : tintFor(item))}>
        <KindIcon kind={item.kind} />
      </span>
      <span className="min-w-0 flex-1 truncate font-medium">{item.name}</span>
      {isFolder && (
        <span className={"flex-shrink-0 text-[12px] " + (active ? "text-white/80" : "text-muted")}>›</span>
      )}
      {!isFolder && onDelete && (
        <button
          type="button"
          onClick={(e) => {
            e.stopPropagation();
            void onDelete(item);
          }}
          className={
            "flex-shrink-0 cursor-pointer rounded p-0.5 opacity-0 transition focus-visible:opacity-100 group-hover:opacity-100 " +
            (active ? "text-white hover:bg-white/10" : "text-muted hover:bg-raised hover:text-red-600")
          }
          title="Delete"
          aria-label="Delete"
        >
          <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <polyline points="3 6 5 6 21 6" />
            <path d="M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6" />
          </svg>
        </button>
      )}
    </div>
  );
}

function PreviewPanel({
  selected,
  onOpen,
  onDelete,
}: {
  selected: GridItem | null;
  onOpen: () => void;
  onDelete?: () => void;
}) {
  if (!selected || selected.kind === "folder") {
    return (
      <aside className="hidden w-[280px] flex-shrink-0 flex-col border-l border-border bg-surface/40 p-4 text-[12.5px] text-muted lg:flex">
        <div className="flex h-full items-center justify-center text-center">
          Select an item to preview its details.
        </div>
      </aside>
    );
  }
  return (
    <aside className="hidden w-[280px] flex-shrink-0 flex-col border-l border-border bg-surface/40 lg:flex">
      <div className="flex flex-1 flex-col gap-4 overflow-y-auto p-5">
        <div className={"inline-flex h-12 w-12 items-center justify-center rounded-md border border-border bg-base " + tintFor(selected)}>
          <KindIcon kind={selected.kind} />
        </div>
        <div>
          <h3 className="break-words font-display text-[16px] font-semibold leading-snug text-foreground">
            {selected.name}
          </h3>
          <p className="mt-0.5 text-[12px] text-muted">{kindLabel(selected)}</p>
        </div>
        <dl className="grid grid-cols-[80px_minmax(0,1fr)] gap-x-3 gap-y-1.5 text-[12px]">
          {selected.sizeBytes != null && (
            <>
              <dt className="text-muted">Size</dt>
              <dd className="text-foreground">{formatBytes(selected.sizeBytes)}</dd>
            </>
          )}
          <dt className="text-muted">Modified</dt>
          <dd className="text-foreground">{formatAbsolute(selected.updatedAt)}</dd>
          {selected.contentType && (
            <>
              <dt className="text-muted">Type</dt>
              <dd className="break-all text-foreground">{selected.contentType}</dd>
            </>
          )}
        </dl>
      </div>
      <div className="flex items-center gap-2 border-t border-border bg-base/60 px-4 py-2.5">
        <button
          type="button"
          onClick={onOpen}
          className="flex-1 cursor-pointer rounded-md border border-border bg-base px-3 py-1 text-[12px] font-medium text-foreground hover:bg-raised"
        >
          Open
        </button>
        {onDelete && (
          <button
            type="button"
            onClick={onDelete}
            className="cursor-pointer rounded-md border border-red-300/60 bg-red-500/5 px-3 py-1 text-[12px] text-red-600 hover:bg-red-500/10"
            title="Move to trash"
          >
            Delete
          </button>
        )}
      </div>
    </aside>
  );
}

function folderContentsToItems(contents: FolderContents): GridItem[] {
  return [
    ...contents.subfolders.map<GridItem>((sub) => ({
      kind: "folder",
      id: sub.id,
      name: sub.name,
      subtitle: `${sub.page_count + sub.file_count} item${sub.page_count + sub.file_count === 1 ? "" : "s"}`,
      updatedAt: sub.created_at,
    })),
    ...contents.pages.map<GridItem>((p) => ({
      kind: "page",
      id: p.id,
      name: p.name.replace(/\.md$/, ""),
      subtitle: p.name.toLowerCase().endsWith(".html") ? "html page" : "page",
      updatedAt: p.created_at,
    })),
    ...contents.files.map<GridItem>((f) => {
      const isCsvLinked = !!(f.content_type.includes("csv") && f.linked_table_id);
      return {
        kind: isCsvLinked ? "table" : "file",
        id: f.id,
        name: f.name,
        subtitle: `${f.content_type || "file"} · ${formatBytes(f.size_bytes)}`,
        sizeBytes: f.size_bytes,
        contentType: f.content_type,
        tableId: f.linked_table_id ?? undefined,
        tableBackedBy: isCsvLinked ? "file" : undefined,
        updatedAt: f.created_at,
      };
    }),
    ...contents.tables.map<GridItem>((t) => ({
      kind: "datatable",
      id: t.id,
      name: t.name,
      subtitle: `table · ${t.row_count} row${t.row_count === 1 ? "" : "s"}`,
      updatedAt: t.created_at,
    })),
  ];
}

function kindLabel(item: GridItem): string {
  if (item.kind === "folder") return "Folder";
  if (item.kind === "table" || item.kind === "datatable") return "Table";
  if (item.kind === "html") return "HTML page";
  if (item.kind === "page") return "Page";
  if (item.contentType?.includes("pdf")) return "PDF";
  if (item.contentType?.includes("csv")) return "CSV";
  if (item.contentType?.startsWith("image/")) {
    return `Image · ${item.contentType.replace("image/", "").toUpperCase()}`;
  }
  return item.contentType || "File";
}

function formatBytes(bytes: number | undefined): string {
  if (bytes == null) return "—";
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}

function formatAbsolute(iso: string | undefined): string {
  if (!iso) return "—";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "—";
  return d.toLocaleDateString(undefined, {
    year: "numeric",
    month: "short",
    day: "numeric",
  });
}
