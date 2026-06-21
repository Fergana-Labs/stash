"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useState, type DragEvent } from "react";
import {
  getMyRecents,
  listSharedWithMe,
  updateFile,
  updateFolder,
  updatePage,
  type RecentEntry,
  type SharedWithMeItem,
} from "../../lib/api";
import { KindIcon, tintFor, type ItemKind } from "./file-browser/kind";

// Shared folders/pages/files/tables surfaced inside the Files source. Session
// folders are handled in the Agent Sessions view, not here.
const FILE_KINDS = new Set<SharedWithMeItem["object_type"]>(["folder", "page", "file", "table"]);

const ITEM_KIND: Record<string, ItemKind> = {
  folder: "folder",
  page: "page",
  file: "file",
  table: "datatable",
};
const LABEL: Record<string, string> = {
  folder: "Folder",
  page: "Page",
  file: "File",
  table: "Table",
};

// Drag payload for shared items. Distinct from the main browser's FB_DRAG_MIME
// because shared items carry their owner — moves run against it, and items can
// only move within the same owner's scope.
const SHARED_DRAG_MIME = "application/x-skill-shared-item";

interface SharedDragPayload {
  object_type: SharedWithMeItem["object_type"];
  object_id: string;
  owner_user_id: string;
}

// Shared tables stay non-draggable.
function isDraggable(item: SharedWithMeItem): boolean {
  return item.object_type !== "table" && item.permission === "write";
}

// SharedWithMeItem has no updated_at, so the columns are Name / Shared by /
// Type rather than the main list's Name / Modified / Type.
const GRID_COLS = "minmax(0,2fr) minmax(0,1fr) minmax(0,1fr)";

function hrefFor(item: SharedWithMeItem): string {
  if (item.object_type === "page") return `/p/${item.object_id}`;
  if (item.object_type === "file") return `/f/${item.object_id}`;
  if (item.object_type === "table") return `/tables/${item.object_id}`;
  return `/folders/${item.object_id}`;
}

function startSharedDrag(e: DragEvent<HTMLElement>, item: SharedWithMeItem) {
  const payload: SharedDragPayload = {
    object_type: item.object_type,
    object_id: item.object_id,
    owner_user_id: item.owner_user_id,
  };
  e.dataTransfer.setData(SHARED_DRAG_MIME, JSON.stringify(payload));
  e.dataTransfer.effectAllowed = "move";
}

function isSharedDrag(e: DragEvent<HTMLElement>): boolean {
  return e.dataTransfer.types.includes(SHARED_DRAG_MIME);
}

export default function SharedWithMeFiles() {
  const [items, setItems] = useState<SharedWithMeItem[]>([]);
  const [recents, setRecents] = useState<RecentEntry[]>([]);
  const [loaded, setLoaded] = useState(false);
  const [error, setError] = useState("");

  const load = useCallback(() => {
    listSharedWithMe()
      .then((all) => setItems(all.filter((i) => FILE_KINDS.has(i.object_type))))
      .catch(() => setItems([]))
      .finally(() => setLoaded(true));
    getMyRecents()
      .then(setRecents)
      .catch(() => setRecents([]));
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  // Recently-viewed shared items: /me/recents spans everything I've opened, so
  // its intersection with the share list is exactly "shared things I opened".
  const recentItems = useMemo(() => {
    const byId = new Map(items.map((item) => [item.object_id, item]));
    return recents
      .map((entry) => byId.get(entry.object_id))
      .filter((item): item is SharedWithMeItem => !!item)
      .slice(0, 8);
  }, [items, recents]);

  // Move a dragged shared item into a shared folder. Both belong to the same
  // owner — the backend allows this through the write share.
  async function moveInto(payload: SharedDragPayload, folder: SharedWithMeItem) {
    if (payload.object_id === folder.object_id) return;
    if (payload.owner_user_id !== folder.owner_user_id) {
      setError("Items can only move within their owner's scope.");
      return;
    }
    setError("");
    try {
      if (payload.object_type === "folder") {
        await updateFolder(payload.object_id, { parent_folder_id: folder.object_id });
      } else if (payload.object_type === "page") {
        await updatePage(payload.object_id, { folder_id: folder.object_id });
      } else {
        await updateFile(payload.object_id, { folder_id: folder.object_id });
      }
      load();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Move failed");
    }
  }

  function dropHandlers(item: SharedWithMeItem, setOver: (v: boolean) => void) {
    // Only writable folders accept drops — a read-only share would reject the
    // move server-side anyway.
    if (item.object_type !== "folder" || item.permission !== "write") return {};
    return {
      onDragOver: (e: DragEvent<HTMLElement>) => {
        if (!isSharedDrag(e)) return;
        e.preventDefault();
        e.dataTransfer.dropEffect = "move";
        setOver(true);
      },
      onDragLeave: () => setOver(false),
      onDrop: (e: DragEvent<HTMLElement>) => {
        setOver(false);
        const raw = e.dataTransfer.getData(SHARED_DRAG_MIME);
        if (!raw) return;
        e.preventDefault();
        try {
          void moveInto(JSON.parse(raw) as SharedDragPayload, item);
        } catch {
          /* malformed */
        }
      },
    };
  }

  if (!loaded) return null;

  if (items.length === 0) {
    return (
      <p className="rounded-lg border border-dashed border-border bg-surface/30 px-4 py-10 text-center text-[12.5px] text-muted">
        Nothing shared with you yet. Folders, pages, files, and tables others
        share with you show up here.
      </p>
    );
  }

  return (
    <div>
      {error && (
        <div className="mb-3 rounded-lg border border-red-300/40 bg-red-500/10 px-4 py-2 text-[13px] text-red-500">
          {error}
        </div>
      )}
      {recentItems.length > 0 && (
        <section className="mb-5">
          <h2 className="m-0 mb-2 text-[11px] font-semibold uppercase tracking-wide text-muted">
            Recent
          </h2>
          <div className="flex flex-wrap gap-2.5">
            {recentItems.map((item) => (
              <RecentCard
                key={`${item.object_type}:${item.object_id}`}
                item={item}
                dropHandlers={dropHandlers}
              />
            ))}
          </div>
        </section>
      )}
      <div className="overflow-hidden rounded-xl border border-border bg-surface">
        <div
          className="grid items-center gap-3 border-b border-border bg-base/60 px-4 py-2.5 text-[11px] font-medium uppercase tracking-wide text-muted"
          style={{ gridTemplateColumns: GRID_COLS }}
        >
          <span>Name</span>
          <span>Shared by</span>
          <span>Type</span>
        </div>
        {items.map((item) => (
          <SharedRow
            key={`${item.object_type}:${item.object_id}`}
            item={item}
            dropHandlers={dropHandlers}
          />
        ))}
      </div>
    </div>
  );
}

type DropHandlers = (
  item: SharedWithMeItem,
  setOver: (v: boolean) => void,
) => Record<string, unknown>;

function SharedRow({ item, dropHandlers }: { item: SharedWithMeItem; dropHandlers: DropHandlers }) {
  const [over, setOver] = useState(false);
  const kind = ITEM_KIND[item.object_type];
  return (
    <Link
      href={hrefFor(item)}
      draggable={isDraggable(item)}
      onDragStart={(e: DragEvent<HTMLAnchorElement>) => startSharedDrag(e, item)}
      {...dropHandlers(item, setOver)}
      className={
        "grid items-center gap-3 border-b border-border-subtle px-4 py-2 text-[13px] last:border-b-0 hover:bg-[var(--color-brand-50)]/50" +
        (over ? " ring-1 ring-inset ring-[var(--color-brand-300)]" : "")
      }
      style={{ gridTemplateColumns: GRID_COLS }}
    >
      <div className="flex min-w-0 items-center gap-2.5">
        <span
          className={
            "flex h-4 w-4 flex-shrink-0 items-center justify-center " +
            tintFor({ kind, id: item.object_id, name: item.name, subtitle: "" })
          }
        >
          <KindIcon kind={kind} />
        </span>
        <span className="min-w-0 truncate font-medium text-foreground">{item.name}</span>
      </div>
      <span className="truncate text-[12px] text-muted">{item.shared_by || "—"}</span>
      <span className="flex items-center gap-2 text-[12px] text-muted">
        {LABEL[item.object_type]}
        {item.permission === "write" && (
          <span className="rounded bg-raised px-1.5 py-0.5 text-[10.5px] uppercase tracking-wide">
            can edit
          </span>
        )}
      </span>
    </Link>
  );
}

// Compact quick-access card, mirroring the My-files Recent strip (minus the
// pin button — pins live with your own files, not shared ones).
function RecentCard({ item, dropHandlers }: { item: SharedWithMeItem; dropHandlers: DropHandlers }) {
  const [over, setOver] = useState(false);
  const kind = ITEM_KIND[item.object_type];
  return (
    <Link
      href={hrefFor(item)}
      draggable={isDraggable(item)}
      onDragStart={(e: DragEvent<HTMLAnchorElement>) => startSharedDrag(e, item)}
      {...dropHandlers(item, setOver)}
      className={
        "flex w-[180px] items-center gap-2.5 rounded-lg border bg-surface px-3 py-2.5 transition hover:border-[var(--color-brand-300)] hover:bg-raised " +
        (over ? "border-[var(--color-brand-300)] ring-1 ring-inset ring-[var(--color-brand-300)]" : "border-border")
      }
    >
      <span
        className={
          "flex h-5 w-5 shrink-0 items-center justify-center " +
          tintFor({ kind, id: item.object_id, name: item.name, subtitle: "" })
        }
      >
        <KindIcon kind={kind} />
      </span>
      <span className="min-w-0 flex-1">
        <span className="block truncate text-[12.5px] font-medium text-foreground">
          {item.name}
        </span>
        <span className="block truncate text-[10.5px] text-muted">
          {LABEL[item.object_type]}
          {item.shared_by ? ` · from ${item.shared_by}` : ""}
        </span>
      </span>
    </Link>
  );
}
