"use client";

import { useState, type DragEvent } from "react";
import {
  FB_DRAG_MIME,
  type FBDragPayload,
} from "./WorkspaceFileBrowser";
import { FileIcon, FolderIcon, PageIcon, PinIcon, TableIcon } from "../../StashIcons";
import type { GridItem, ItemKind } from "./FolderItemGrid";

// Tailwind v4 doesn't generate this `grid-cols-[…]` class reliably when
// minmax() with commas is the first column token, so set the template via
// inline style. Keeps the four-column Drive-style layout: name takes 2fr,
// modified + type each take 1fr, action button is fixed 36px.
const LIST_GRID_COLS = "minmax(0,2fr) minmax(0,1fr) minmax(0,1fr) 64px";

interface Props {
  items: GridItem[];
  onNavigate: (item: GridItem) => void;
  onReparent: (payload: FBDragPayload, targetFolderId: string | null) => Promise<void>;
  onDelete: (item: GridItem) => Promise<void>;
  isPinned: (item: GridItem) => boolean;
  onTogglePin: (item: GridItem) => void;
}

// Google-Drive-style list: Name / Modified / Type / actions, rendered as a
// floating rounded card rather than a full-bleed table. Hover reveals pin +
// trash buttons in the action column. Folders + files + pages all live in the
// same grid; folders surface their child-count in the Type column instead of a
// modified date.
export default function ItemsList({
  items,
  onNavigate,
  onReparent,
  onDelete,
  isPinned,
  onTogglePin,
}: Props) {
  return (
    <div className="scroll-thin overflow-hidden rounded-xl border border-border bg-surface">
      <div
        className="grid items-center gap-3 border-b border-border bg-base/60 px-4 py-2.5 text-[11px] font-medium uppercase tracking-wide text-muted"
        style={{ gridTemplateColumns: LIST_GRID_COLS }}
      >
        <span>Name</span>
        <span>Modified</span>
        <span>Type</span>
        <span />
      </div>
      <div>
        {items.map((item) => (
          <Row
            key={`${item.kind}-${item.id}`}
            item={item}
            onNavigate={onNavigate}
            onReparent={onReparent}
            onDelete={onDelete}
            pinned={isPinned(item)}
            onTogglePin={onTogglePin}
          />
        ))}
        {items.length === 0 && (
          <div className="px-4 py-10 text-center text-[12.5px] text-muted">
            Empty folder.
          </div>
        )}
      </div>
    </div>
  );
}

function Row({
  item,
  onNavigate,
  onReparent,
  onDelete,
  pinned,
  onTogglePin,
}: {
  item: GridItem;
  onNavigate: (item: GridItem) => void;
  onReparent: (payload: FBDragPayload, targetFolderId: string | null) => Promise<void>;
  onDelete: (item: GridItem) => Promise<void>;
  pinned: boolean;
  onTogglePin: (item: GridItem) => void;
}) {
  const [over, setOver] = useState(false);
  const isFolder = item.kind === "folder";

  return (
    <div
      onClick={() => onNavigate(item)}
      role="button"
      tabIndex={0}
      onKeyDown={(e) => {
        if (e.key === "Enter") onNavigate(item);
      }}
      draggable
      onDragStart={(e: DragEvent<HTMLDivElement>) => {
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
          const payload = JSON.parse(raw) as FBDragPayload;
          if (payload.kind === "folder" && payload.id === item.id) return;
          onReparent(payload, item.id);
        } catch {
          /* malformed */
        }
      }}
      className={
        "group grid cursor-pointer select-none items-center gap-3 border-b border-border-subtle px-4 py-2 text-[13px] last:border-b-0 hover:bg-[var(--color-brand-50)]/50 " +
        (over ? "ring-1 ring-inset ring-[var(--color-brand-300)]" : "")
      }
      style={{ gridTemplateColumns: LIST_GRID_COLS }}
    >
      <div className="flex min-w-0 items-center gap-2.5">
        <span className={"flex h-4 w-4 flex-shrink-0 items-center justify-center " + tintFor(item)}>
          <KindIcon kind={item.kind} />
        </span>
        <span className="min-w-0 truncate font-medium text-foreground">{item.name}</span>
      </div>
      <span className="truncate text-[12px] text-muted">{formatRelative(item.updatedAt)}</span>
      <span className="truncate text-[12px] text-muted">{typeFor(item)}</span>
      <div className="flex items-center justify-end gap-0.5">
        <button
          type="button"
          onClick={(e) => {
            e.stopPropagation();
            onTogglePin(item);
          }}
          className={
            "rounded p-1 transition hover:bg-raised " +
            (pinned
              ? "text-[var(--color-brand-600)] hover:text-[var(--color-brand-700)]"
              : "text-muted opacity-0 hover:text-foreground focus-visible:opacity-100 group-hover:opacity-100")
          }
          title={pinned ? "Unpin" : "Pin"}
          aria-label={pinned ? "Unpin" : "Pin"}
          aria-pressed={pinned}
        >
          <PinIcon className="text-[15px]" />
        </button>
        <button
          type="button"
          onClick={(e) => {
            e.stopPropagation();
            void onDelete(item);
          }}
          className="rounded p-1 text-muted opacity-0 transition hover:bg-raised hover:text-red-600 focus-visible:opacity-100 group-hover:opacity-100"
          title="Delete"
          aria-label="Delete"
        >
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
            <polyline points="3 6 5 6 21 6" />
            <path d="M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6" />
            <path d="M10 11v6" />
            <path d="M14 11v6" />
            <path d="M9 6V4a2 2 0 0 1 2-2h2a2 2 0 0 1 2 2v2" />
          </svg>
        </button>
      </div>
    </div>
  );
}

export function KindIcon({ kind }: { kind: ItemKind }) {
  if (kind === "folder") return <FolderIcon />;
  if (kind === "page" || kind === "html") return <PageIcon />;
  if (kind === "table") return <TableIcon />;
  return <FileIcon />;
}

export function tintFor(item: GridItem): string {
  if (item.kind === "folder") return "text-muted";
  if (item.kind === "html") return "text-[#D97706]";
  if (item.kind === "table") return "text-emerald-600";
  if (item.contentType?.includes("pdf")) return "text-rose-500";
  if (item.contentType?.startsWith("image/")) return "text-[var(--color-brand-600)]";
  if (item.kind === "page") return "text-[var(--color-brand-600)]";
  return "text-muted";
}

export function typeFor(item: GridItem): string {
  if (item.kind === "folder") return item.subtitle;
  if (item.kind === "table") return "Table";
  if (item.kind === "html") return "HTML page";
  if (item.kind === "page") return "Page";
  if (item.contentType?.includes("pdf")) return "PDF";
  if (item.contentType?.includes("csv")) return "CSV";
  if (item.contentType?.startsWith("image/")) {
    return item.contentType.replace("image/", "").toUpperCase();
  }
  return item.contentType || "File";
}

function formatRelative(iso: string | undefined): string {
  if (!iso) return "—";
  const then = new Date(iso).getTime();
  if (Number.isNaN(then)) return "—";
  const diffMs = Date.now() - then;
  const diffMin = Math.round(diffMs / 60000);
  if (diffMin < 1) return "just now";
  if (diffMin < 60) return `${diffMin}m ago`;
  const diffH = Math.round(diffMin / 60);
  if (diffH < 24) return `${diffH}h ago`;
  const diffD = Math.round(diffH / 24);
  if (diffD < 7) return `${diffD}d ago`;
  return new Date(iso).toLocaleDateString(undefined, {
    month: "short",
    day: "numeric",
    year: new Date(iso).getFullYear() === new Date().getFullYear() ? undefined : "numeric",
  });
}
