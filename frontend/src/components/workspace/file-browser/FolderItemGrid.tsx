"use client";

import { useState, type DragEvent } from "react";
import { FileIcon, FolderIcon, PageIcon, TableIcon } from "../../StashIcons";
import { FB_DRAG_MIME, type FBDragPayload } from "./WorkspaceFileBrowser";

export type ItemKind = "folder" | "page" | "html" | "table" | "file";

export interface GridItem {
  kind: ItemKind;
  id: string;
  name: string;
  subtitle: string;
  sizeBytes?: number;
  contentType?: string;
  linkedTableId?: string;
}

interface Props {
  items: GridItem[];
  selectedId: string | null;
  onSelect: (item: GridItem) => void;
  onNavigate: (item: GridItem) => void;
  onReparent: (payload: FBDragPayload, targetFolderId: string | null) => Promise<void>;
}

export default function FolderItemGrid({
  items,
  selectedId,
  onSelect,
  onNavigate,
  onReparent,
}: Props) {
  if (items.length === 0) {
    return (
      <div className="flex items-center justify-center bg-base p-12">
        <div className="rounded-lg border border-dashed border-border bg-surface/30 px-6 py-10 text-center text-[12.5px] text-muted">
          Empty folder. Add a page, upload a file, or create a subfolder.
        </div>
      </div>
    );
  }

  return (
    <div className="scroll-thin overflow-y-auto bg-base p-4">
      <div className="grid grid-cols-1 gap-2.5 sm:grid-cols-2 xl:grid-cols-3">
        {items.map((item) => (
          <Tile
            key={`${item.kind}-${item.id}`}
            item={item}
            selected={item.id === selectedId}
            onSelect={() => onSelect(item)}
            onNavigate={() => onNavigate(item)}
            onReparent={onReparent}
          />
        ))}
      </div>
    </div>
  );
}

function Tile({
  item,
  selected,
  onSelect,
  onNavigate,
  onReparent,
}: {
  item: GridItem;
  selected: boolean;
  onSelect: () => void;
  onNavigate: () => void;
  onReparent: (payload: FBDragPayload, targetFolderId: string | null) => Promise<void>;
}) {
  const [over, setOver] = useState(false);
  const isFolder = item.kind === "folder";

  return (
    <div
      onClick={onSelect}
      onDoubleClick={onNavigate}
      role="button"
      tabIndex={0}
      onKeyDown={(e) => {
        if (e.key === "Enter") onNavigate();
      }}
      // Drag source — payload identifies kind + id so the drop handler knows
      // which API to call.
      draggable
      onDragStart={(e: DragEvent<HTMLDivElement>) => {
        const payload: FBDragPayload = { kind: item.kind, id: item.id };
        e.dataTransfer.setData(FB_DRAG_MIME, JSON.stringify(payload));
        e.dataTransfer.effectAllowed = "move";
      }}
      // Folder tiles are also drop targets — drop a sibling onto a folder
      // tile to move it into that folder.
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
        "group flex items-start gap-3 rounded-lg border bg-base p-3 transition cursor-pointer select-none " +
        (selected
          ? "border-[var(--color-brand-400)] bg-[var(--color-brand-50)]/40"
          : "border-border hover:border-[var(--color-brand-200)] hover:bg-[var(--color-brand-50)]/30") +
        (over ? " ring-2 ring-[var(--color-brand-300)]" : "")
      }
    >
      <span className={"mt-0.5 " + tintFor(item)}>
        <KindIcon kind={item.kind} />
      </span>
      <div className="min-w-0 flex-1">
        <div className="truncate text-[13.5px] font-semibold text-foreground">{item.name}</div>
        <div className="mt-0.5 truncate text-[11.5px] text-muted">{item.subtitle}</div>
      </div>
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
