"use client";

import { useState, type DragEvent } from "react";
import { FileIcon, FolderIcon, PageIcon, TableIcon } from "../../StashIcons";
import { FB_DRAG_MIME, type FBDragPayload } from "./WorkspaceFileBrowser";
import type { GridItem, ItemKind } from "./FolderItemGrid";

interface Props {
  items: GridItem[];
  onNavigate: (item: GridItem) => void;
  onReparent: (payload: FBDragPayload, targetFolderId: string | null) => Promise<void>;
  onDelete: (item: GridItem) => Promise<void>;
}

// Dense list view: one item per row with kind icon, name, subtitle, and
// a hover-only delete affordance. Same drag-drop semantics as Grid.
export default function ItemsList({ items, onNavigate, onReparent, onDelete }: Props) {
  if (items.length === 0) {
    return (
      <div className="flex items-center justify-center bg-base p-12">
        <div className="rounded-lg border border-dashed border-border bg-surface/30 px-6 py-10 text-center text-[12.5px] text-muted">
          Empty folder.
        </div>
      </div>
    );
  }

  return (
    <div className="scroll-thin overflow-y-auto bg-base">
      <div className="grid grid-cols-[20px_minmax(0,1fr)_minmax(0,1fr)_28px] gap-3 border-b border-border bg-surface px-4 py-2 text-[10px] font-medium uppercase tracking-[0.08em] text-muted">
        <span />
        <span>Name</span>
        <span>Type / size</span>
        <span />
      </div>
      {items.map((item) => (
        <Row
          key={`${item.kind}-${item.id}`}
          item={item}
          onNavigate={onNavigate}
          onReparent={onReparent}
          onDelete={onDelete}
        />
      ))}
    </div>
  );
}

function Row({
  item,
  onNavigate,
  onReparent,
  onDelete,
}: {
  item: GridItem;
  onNavigate: (item: GridItem) => void;
  onReparent: (payload: FBDragPayload, targetFolderId: string | null) => Promise<void>;
  onDelete: (item: GridItem) => Promise<void>;
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
        "group grid cursor-pointer select-none grid-cols-[20px_minmax(0,1fr)_minmax(0,1fr)_28px] items-center gap-3 border-b border-border-subtle px-4 py-2 text-[13px] hover:bg-[var(--color-brand-50)]/30 " +
        (over ? "ring-1 ring-inset ring-[var(--color-brand-300)]" : "")
      }
    >
      <span className={tintFor(item)}>
        <KindIcon kind={item.kind} />
      </span>
      <span className="min-w-0 truncate font-medium text-foreground">{item.name}</span>
      <span className="min-w-0 truncate text-[12px] text-muted">{item.subtitle}</span>
      <button
        type="button"
        onClick={(e) => {
          e.stopPropagation();
          void onDelete(item);
        }}
        className="rounded p-1 text-muted opacity-0 hover:bg-raised hover:text-red-600 group-hover:opacity-100"
        title="Delete"
        aria-label="Delete"
      >
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
          <path d="M3 6h18M8 6V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6" />
        </svg>
      </button>
    </div>
  );
}

function KindIcon({ kind }: { kind: ItemKind }) {
  if (kind === "folder") return <FolderIcon />;
  if (kind === "page" || kind === "html") return <PageIcon />;
  if (kind === "table") return <TableIcon />;
  return <FileIcon />;
}

function tintFor(item: GridItem): string {
  if (item.kind === "folder") return "text-muted";
  if (item.kind === "html") return "text-[#D97706]";
  if (item.kind === "table") return "text-emerald-600";
  if (item.contentType?.includes("pdf")) return "text-rose-500";
  if (item.contentType?.includes("image")) return "text-violet-600";
  return "text-muted";
}
