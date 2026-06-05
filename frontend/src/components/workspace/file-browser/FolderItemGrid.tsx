"use client";

import { useState, type DragEvent } from "react";
import { shouldOpenInNewTab, type NavigateOptions } from "../../../lib/linkNavigation";
import { FileIcon, FolderIcon, PageIcon, TableIcon } from "../../StashIcons";
import { type FBDragPayload } from "./WorkspaceFileBrowser";
import { SelectBox, handleFolderDrop, isFbDrag, startItemDrag } from "./ItemsList";

// "table" = a CSV/spreadsheet *file* linked to a table; "datatable" = a
// standalone structured-data table (the `tables` entity). Both render with the
// table icon, but they have different backing rows so move/delete/nav differ.
export type ItemKind = "folder" | "page" | "html" | "table" | "datatable" | "file";

export interface GridItem {
  kind: ItemKind;
  id: string;
  name: string;
  subtitle: string;
  sizeBytes?: number;
  contentType?: string;
  tableId?: string;
  tableBackedBy?: "file" | "table";
  linkedTableId?: string;
  movable?: boolean;
  /** ISO timestamp. Renders as "Modified" in the Drive-style List view.
   *  Not all rows have one — FolderContents.pages currently omits it. */
  updatedAt?: string;
}

interface Props {
  items: GridItem[];
  selectedId: string | null;
  onSelect: (item: GridItem, options?: NavigateOptions) => void;
  onNavigate: (item: GridItem, options?: NavigateOptions) => void;
  onReparent: (payload: FBDragPayload, targetFolderId: string | null) => Promise<void>;
  onReparentMany?: (payloads: FBDragPayload[], targetFolderId: string | null) => Promise<void>;
  onDelete?: (item: GridItem) => Promise<void>;
  selectedIds?: Set<string>;
  onToggleSelect?: (item: GridItem) => void;
  selectedDragPayloads?: FBDragPayload[];
}

export default function FolderItemGrid({
  items,
  selectedId,
  onSelect,
  onNavigate,
  onReparent,
  onReparentMany,
  onDelete,
  selectedIds,
  onToggleSelect,
  selectedDragPayloads = [],
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
    <div className="scroll-thin overflow-y-auto bg-base">
      <div className="grid grid-cols-1 gap-2.5 sm:grid-cols-2 xl:grid-cols-3">
        {items.map((item) => (
          <Tile
            key={`${item.kind}-${item.id}`}
            item={item}
            selected={item.id === selectedId}
            multiSelected={!!selectedIds?.has(item.id)}
            onSelect={(options) => onSelect(item, options)}
            onNavigate={(options) => onNavigate(item, options)}
            onReparent={onReparent}
            onReparentMany={onReparentMany}
            onDelete={onDelete}
            onToggleSelect={onToggleSelect ? () => onToggleSelect(item) : undefined}
            selectedDragPayloads={selectedDragPayloads}
          />
        ))}
      </div>
    </div>
  );
}

function Tile({
  item,
  selected,
  multiSelected,
  onSelect,
  onNavigate,
  onReparent,
  onReparentMany,
  onDelete,
  onToggleSelect,
  selectedDragPayloads,
}: {
  item: GridItem;
  selected: boolean;
  multiSelected: boolean;
  onSelect: (options?: NavigateOptions) => void;
  onNavigate: (options?: NavigateOptions) => void;
  onReparent: (payload: FBDragPayload, targetFolderId: string | null) => Promise<void>;
  onReparentMany?: (payloads: FBDragPayload[], targetFolderId: string | null) => Promise<void>;
  onDelete?: (item: GridItem) => Promise<void>;
  onToggleSelect?: () => void;
  selectedDragPayloads: FBDragPayload[];
}) {
  const [over, setOver] = useState(false);
  const isFolder = item.kind === "folder";

  return (
    <div
      onClick={(e) => onSelect({ newTab: shouldOpenInNewTab(e) })}
      onAuxClick={(e) => {
        if (shouldOpenInNewTab(e)) onSelect({ newTab: true });
      }}
      onDoubleClick={() => onNavigate()}
      role="button"
      tabIndex={0}
      onKeyDown={(e) => {
        if (e.key === "Enter") onNavigate();
      }}
      // Drag source — carries the multi-selection when this tile is part of
      // one, else just this item.
      draggable={item.movable !== false}
      onDragStart={(e: DragEvent<HTMLDivElement>) =>
        startItemDrag(e, item, multiSelected, selectedDragPayloads)
      }
      // Folder tiles are also drop targets — drop a sibling (or a whole
      // selection) onto a folder tile to move it in.
      onDragOver={(e) => {
        if (!isFolder) return;
        if (!isFbDrag(e)) return;
        e.preventDefault();
        e.dataTransfer.dropEffect = "move";
        setOver(true);
      }}
      onDragLeave={() => setOver(false)}
      onDrop={(e) => {
        if (!isFolder) return;
        setOver(false);
        e.preventDefault();
        handleFolderDrop(e, item.id, onReparent, onReparentMany ?? (async () => {}));
      }}
      className={
        "group flex items-start gap-3 rounded-lg border bg-base p-3 transition cursor-pointer select-none " +
        (selected || multiSelected
          ? "border-[var(--color-brand-400)] bg-[var(--color-brand-50)]/40"
          : "border-border hover:border-[var(--color-brand-200)] hover:bg-[var(--color-brand-50)]/30") +
        (over ? " ring-2 ring-[var(--color-brand-300)]" : "")
      }
    >
      {onToggleSelect && (
        <span className="mt-0.5">
          <SelectBox selected={multiSelected} onToggle={onToggleSelect} />
        </span>
      )}
      <span className={"mt-0.5 " + tintFor(item)}>
        <KindIcon kind={item.kind} />
      </span>
      <div className="min-w-0 flex-1">
        <div className="truncate text-[13.5px] font-semibold text-foreground">{item.name}</div>
        <div className="mt-0.5 truncate text-[11.5px] text-muted">{item.subtitle}</div>
      </div>
      {onDelete && (
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
      )}
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
  if (item.contentType?.includes("image")) return "text-[var(--color-brand-600)]";
  return "text-muted";
}
