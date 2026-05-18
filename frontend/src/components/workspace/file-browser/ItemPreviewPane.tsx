"use client";

import EditableTitle from "../EditableTitle";
import { FileIcon, FolderIcon, PageIcon, TableIcon } from "../../StashIcons";
import type { ItemKind } from "./FolderItemGrid";

export interface PreviewSelection {
  kind: ItemKind;
  id: string;
  name: string;
  subtitle: string;
  sizeBytes?: number;
  linkedTableId?: string;
}

interface Props {
  workspaceId: string;
  selection: PreviewSelection | null;
  onOpen: (s: PreviewSelection) => void;
  onDelete: (s: PreviewSelection) => Promise<void>;
  onRename: (s: PreviewSelection, next: string) => Promise<string>;
}

export default function ItemPreviewPane({
  workspaceId,
  selection,
  onOpen,
  onDelete,
  onRename,
}: Props) {
  void workspaceId; // currently unused; kept for future deep-link actions
  if (!selection) {
    return (
      <aside className="scroll-thin overflow-y-auto bg-surface/30 p-4 text-[12.5px] text-muted">
        <div className="sys-label mb-2">Preview</div>
        <p className="m-0">Click an item in the grid to see details.</p>
        <p className="m-0 mt-2 text-[11.5px]">
          Drag tiles onto folders or the tree to move them.
        </p>
      </aside>
    );
  }

  const labelByKind: Record<ItemKind, string> = {
    folder: "Folder",
    page: "Page",
    html: "HTML page",
    table: "Table",
    file: "File",
  };

  return (
    <aside className="scroll-thin overflow-y-auto bg-surface/30 p-4 text-[12.5px]">
      <div className="sys-label mb-2">Preview</div>
      <div className="rounded-lg border border-border bg-base p-3.5">
        <div className="flex items-start gap-2.5">
          <span className="mt-0.5 text-muted">
            <KindIcon kind={selection.kind} />
          </span>
          <div className="min-w-0 flex-1">
            <div className="break-words text-[14px] font-semibold text-foreground">
              <EditableTitle
                value={selection.name}
                onSave={(next) => onRename(selection, next)}
              />
            </div>
            <div className="mt-0.5 text-[11.5px] text-muted">{selection.subtitle}</div>
          </div>
        </div>

        <dl className="mt-3 space-y-1.5 text-[12px]">
          <Row label="Type" value={labelByKind[selection.kind]} />
          {selection.sizeBytes !== undefined && (
            <Row label="Size" value={formatBytes(selection.sizeBytes)} />
          )}
        </dl>

        <div className="mt-4 flex gap-1.5">
          <button
            type="button"
            onClick={() => onOpen(selection)}
            className="flex-1 rounded-md bg-[var(--color-brand-600)] px-3 py-1.5 text-[12.5px] font-medium text-white hover:bg-[var(--color-brand-700)]"
          >
            Open
          </button>
          <button
            type="button"
            onClick={() => onDelete(selection)}
            className="rounded-md border border-border bg-base px-3 py-1.5 text-[12.5px] text-foreground hover:border-red-300 hover:bg-red-50 hover:text-red-700"
          >
            Delete
          </button>
        </div>
      </div>
    </aside>
  );
}

function Row({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex gap-2">
      <dt className="w-12 shrink-0 text-muted">{label}</dt>
      <dd className="m-0 break-words text-foreground">{value}</dd>
    </div>
  );
}

function KindIcon({ kind }: { kind: ItemKind }) {
  if (kind === "folder") return <FolderIcon />;
  if (kind === "page" || kind === "html") return <PageIcon />;
  if (kind === "table") return <TableIcon />;
  return <FileIcon />;
}

function formatBytes(b: number): string {
  if (!b) return "0 B";
  if (b < 1024) return `${b} B`;
  if (b < 1024 * 1024) return `${(b / 1024).toFixed(1)} KB`;
  return `${(b / 1024 / 1024).toFixed(1)} MB`;
}
