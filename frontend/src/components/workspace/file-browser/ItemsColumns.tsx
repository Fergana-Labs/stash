"use client";

import Link from "next/link";
import { useState, type DragEvent } from "react";
import { FileIcon, FolderIcon, PageIcon, TableIcon } from "../../StashIcons";
import type { FolderContents } from "../../../lib/api";
import type { FolderTreeNode, WorkspaceTree } from "../../../lib/types";
import { FB_DRAG_MIME, type FBDragPayload } from "./WorkspaceFileBrowser";
import type { GridItem, ItemKind } from "./FolderItemGrid";
import { useParams } from "next/navigation";

interface Props {
  workspaceId: string;
  tree: WorkspaceTree | null;
  activeFolderId: string | null;
  currentContents: FolderContents | null;
  currentItems: GridItem[];
  onNavigate: (item: GridItem) => void;
  onReparent: (payload: FBDragPayload, targetFolderId: string | null) => Promise<void>;
}

// Column view: left column is the workspace folder tree (Finder's sidebar),
// right column is the contents of the currently selected folder. Drag-drop
// works in both — drop on a tree node to reparent, drop on a folder tile in
// the right column to nest into it.
export default function ItemsColumns({
  workspaceId,
  tree,
  activeFolderId,
  onNavigate,
  onReparent,
  currentItems,
}: Props) {
  return (
    <div className="grid min-h-0 flex-1 grid-cols-[260px_minmax(0,1fr)] divide-x divide-border">
      <nav className="scroll-thin overflow-y-auto bg-surface/40 px-2 py-3 text-[13px]">
        <RootRow
          workspaceId={workspaceId}
          active={activeFolderId === null}
          onReparent={onReparent}
        />
        {tree?.folders.map((node) => (
          <TreeRow
            key={node.id}
            node={node}
            depth={0}
            workspaceId={workspaceId}
            activeFolderId={activeFolderId}
            onReparent={onReparent}
          />
        ))}
        {tree && tree.folders.length === 0 && (
          <div className="px-2 py-2 text-[11.5px] italic text-muted">No folders yet.</div>
        )}
      </nav>
      <div className="scroll-thin overflow-y-auto bg-base">
        {currentItems.length === 0 ? (
          <div className="flex items-center justify-center p-12">
            <div className="rounded-lg border border-dashed border-border bg-surface/30 px-6 py-10 text-center text-[12.5px] text-muted">
              Empty folder.
            </div>
          </div>
        ) : (
          <div className="divide-y divide-border-subtle">
            {currentItems.map((item) => (
              <ItemRow
                key={`${item.kind}-${item.id}`}
                item={item}
                onNavigate={onNavigate}
                onReparent={onReparent}
              />
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

function RootRow({
  workspaceId,
  active,
  onReparent,
}: {
  workspaceId: string;
  active: boolean;
  onReparent: (payload: FBDragPayload, targetFolderId: string | null) => Promise<void>;
}) {
  const [over, setOver] = useState(false);
  return (
    <Link
      href={`/workspaces/${workspaceId}/files`}
      className={
        "mb-1 flex items-center gap-2 rounded-md px-2 py-1 " +
        (active
          ? "bg-[var(--color-brand-50)] text-[var(--color-brand-800)]"
          : "text-dim hover:bg-raised hover:text-foreground") +
        (over ? " ring-2 ring-[var(--color-brand-300)]" : "")
      }
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
          onReparent(JSON.parse(raw) as FBDragPayload, null);
        } catch {
          /* malformed */
        }
      }}
    >
      <FolderIcon />
      <span className="font-medium">Files</span>
    </Link>
  );
}

function TreeRow({
  node,
  depth,
  workspaceId,
  activeFolderId,
  onReparent,
}: {
  node: FolderTreeNode;
  depth: number;
  workspaceId: string;
  activeFolderId: string | null;
  onReparent: (payload: FBDragPayload, targetFolderId: string | null) => Promise<void>;
}) {
  const [open, setOpen] = useState(activeFolderId === node.id || depth === 0);
  const [over, setOver] = useState(false);
  const active = activeFolderId === node.id;
  return (
    <div>
      <div
        className={
          "flex items-center gap-1 rounded-md px-1 py-0.5 " +
          (active ? "bg-[var(--color-brand-50)] text-[var(--color-brand-800)]" : "hover:bg-raised") +
          (over ? " ring-2 ring-[var(--color-brand-300)]" : "")
        }
        style={{ paddingLeft: 4 + depth * 12 }}
        draggable
        onDragStart={(e: DragEvent<HTMLDivElement>) => {
          const payload: FBDragPayload = { kind: "folder", id: node.id };
          e.dataTransfer.setData(FB_DRAG_MIME, JSON.stringify(payload));
          e.dataTransfer.effectAllowed = "move";
        }}
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
            const p = JSON.parse(raw) as FBDragPayload;
            if (p.kind === "folder" && p.id === node.id) return;
            onReparent(p, node.id);
          } catch {
            /* malformed */
          }
        }}
      >
        <button
          type="button"
          onClick={(e) => {
            e.preventDefault();
            setOpen((o) => !o);
          }}
          className="flex h-4 w-4 items-center justify-center rounded text-muted hover:bg-base/60 hover:text-foreground"
          aria-expanded={open}
          aria-label={open ? "Collapse" : "Expand"}
        >
          {node.folders.length > 0 ? (
            <svg
              className={"h-3 w-3 transition-transform " + (open ? "rotate-90" : "")}
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="2.5"
              strokeLinecap="round"
              strokeLinejoin="round"
            >
              <polyline points="9 18 15 12 9 6" />
            </svg>
          ) : (
            <span className="block h-1 w-1 rounded-full bg-muted/40" />
          )}
        </button>
        <Link
          href={`/workspaces/${workspaceId}/folders/${node.id}`}
          className={
            "flex min-w-0 flex-1 items-center gap-1.5 truncate " +
            (active ? "font-medium" : "text-foreground")
          }
        >
          <FolderIcon />
          <span className="truncate">{node.name}</span>
        </Link>
      </div>
      {open &&
        node.folders.map((child) => (
          <TreeRow
            key={child.id}
            node={child}
            depth={depth + 1}
            workspaceId={workspaceId}
            activeFolderId={activeFolderId}
            onReparent={onReparent}
          />
        ))}
    </div>
  );
}

function ItemRow({
  item,
  onNavigate,
  onReparent,
}: {
  item: GridItem;
  onNavigate: (item: GridItem) => void;
  onReparent: (payload: FBDragPayload, targetFolderId: string | null) => Promise<void>;
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
          const p = JSON.parse(raw) as FBDragPayload;
          if (p.kind === "folder" && p.id === item.id) return;
          onReparent(p, item.id);
        } catch {
          /* malformed */
        }
      }}
      className={
        "flex cursor-pointer select-none items-center gap-3 px-3 py-2 text-[13px] hover:bg-[var(--color-brand-50)]/30 " +
        (over ? "ring-1 ring-inset ring-[var(--color-brand-300)]" : "")
      }
    >
      <span className={tintFor(item)}>
        <KindIcon kind={item.kind} />
      </span>
      <span className="min-w-0 flex-1 truncate font-medium text-foreground">{item.name}</span>
      <span className="hidden text-[11.5px] text-muted sm:inline">{item.subtitle}</span>
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

// Suppress unused-import warning in some build configs (useParams reserved for
// future deep-link behavior — keep import while not actively used).
void useParams;
