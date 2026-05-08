"use client";

import { useState } from "react";
import ShareSheet from "../share/ShareSheet";
import type { ShareableObjectType } from "../../lib/api";
import {
  FolderTreeNode,
  PageSummary,
  WorkspaceTree,
} from "../../lib/types";

interface FileTreeProps {
  tree: WorkspaceTree;
  selectedPageId: string | null;
  onSelectPage: (pageId: string) => void;
  onCreatePage: (folderId: string | null) => void;
  onCreateFolder: (parentFolderId: string | null) => void;
  onDeletePage: (pageId: string) => void;
  onDeleteFolder: (folderId: string) => void;
  onRenamePage: (pageId: string, currentName: string) => void;
  onRenameFolder: (folderId: string, currentName: string) => void;
  onMovePage: (pageId: string, folderId: string | null) => void;
}

type ContextTarget =
  | { type: "page"; id: string; name: string; folderId: string | null }
  | { type: "folder"; id: string; name: string };

interface ContextMenu {
  x: number;
  y: number;
  target: ContextTarget;
}

// Flatten the folder tree into a flat list of {id, label, depth} entries —
// used to render move-to options across nested folders.
function flatFolderList(
  folders: FolderTreeNode[],
  prefix = ""
): { id: string; label: string }[] {
  const out: { id: string; label: string }[] = [];
  for (const f of folders) {
    const label = prefix ? `${prefix}/${f.name}` : f.name;
    out.push({ id: f.id, label });
    if (f.folders.length) out.push(...flatFolderList(f.folders, label));
  }
  return out;
}

export default function FileTreeComponent({
  tree,
  selectedPageId,
  onSelectPage,
  onCreatePage,
  onCreateFolder,
  onDeletePage,
  onDeleteFolder,
  onRenamePage,
  onRenameFolder,
  onMovePage,
}: FileTreeProps) {
  const [collapsed, setCollapsed] = useState<Set<string>>(new Set());
  const [contextMenu, setContextMenu] = useState<ContextMenu | null>(null);
  const [shareSheet, setShareSheet] = useState<{
    x: number;
    y: number;
    objectType: ShareableObjectType;
    objectId: string;
    label: string;
  } | null>(null);

  const toggle = (folderId: string) => {
    setCollapsed((prev) => {
      const next = new Set(prev);
      if (next.has(folderId)) next.delete(folderId);
      else next.add(folderId);
      return next;
    });
  };

  const handleContextMenu = (e: React.MouseEvent, target: ContextTarget) => {
    e.preventDefault();
    setContextMenu({ x: e.clientX, y: e.clientY, target });
  };
  const closeContextMenu = () => setContextMenu(null);

  const renderPage = (page: PageSummary) => {
    const active = selectedPageId === page.id;
    return (
      <button
        key={page.id}
        onClick={() => onSelectPage(page.id)}
        onContextMenu={(e) =>
          handleContextMenu(e, {
            type: "page",
            id: page.id,
            name: page.name,
            folderId: page.folder_id,
          })
        }
        className={
          "flex w-full items-center gap-2 rounded px-2 py-1.5 text-left text-[13px] transition-colors " +
          (active
            ? "bg-brand-muted font-medium text-brand"
            : "text-dim hover:bg-raised hover:text-foreground")
        }
      >
        <span
          className={
            "h-1 w-1 flex-shrink-0 rounded-full " +
            (active ? "opacity-100" : "opacity-40")
          }
          style={{ background: "currentColor" }}
        />
        <span className="truncate">{page.name}</span>
      </button>
    );
  };

  const renderFolder = (folder: FolderTreeNode, depth: number) => {
    const isCollapsed = collapsed.has(folder.id);
    const childCount = folder.folders.length + folder.pages.length;
    return (
      <div key={folder.id} className="mb-2" style={{ paddingLeft: depth * 8 }}>
        <button
          onClick={() => toggle(folder.id)}
          onContextMenu={(e) =>
            handleContextMenu(e, { type: "folder", id: folder.id, name: folder.name })
          }
          className="flex w-full items-center gap-1.5 rounded px-2 py-1 text-left font-mono text-[10px] font-medium uppercase tracking-[0.12em] text-muted transition-colors hover:text-foreground"
        >
          <span
            className={
              "inline-block text-[9px] transition-transform " +
              (isCollapsed ? "" : "rotate-90")
            }
          >
            ▸
          </span>
          <span className="truncate">{folder.name}</span>
          <span className="ml-auto font-mono text-[10px] text-muted">{childCount}</span>
        </button>
        {!isCollapsed && (
          <div className="mt-1">
            {folder.folders.map((sub) => renderFolder(sub, depth + 1))}
            <ul className="space-y-0.5" style={{ paddingLeft: 8 }}>
              {folder.pages.map((p) => (
                <li key={p.id}>{renderPage(p)}</li>
              ))}
              {childCount === 0 && (
                <li className="px-2 py-1 text-[11px] text-muted">Empty folder</li>
              )}
            </ul>
          </div>
        )}
      </div>
    );
  };

  const allFolders = flatFolderList(tree.folders);

  return (
    <div className="flex h-full flex-col" onClick={closeContextMenu}>
      <div className="flex items-center justify-between gap-2 border-b border-border-subtle px-3 py-2.5">
        <p className="font-mono text-[10px] font-medium uppercase tracking-[0.12em] text-muted">
          Pages
        </p>
        <div className="flex gap-1">
          <button
            onClick={() => onCreatePage(null)}
            className="inline-flex h-6 items-center rounded border border-border bg-transparent px-2 font-mono text-[10px] text-dim transition-colors hover:border-foreground hover:text-foreground"
            title="New page at workspace root"
          >
            + Page
          </button>
          <button
            onClick={() => onCreateFolder(null)}
            className="inline-flex h-6 items-center rounded border border-border bg-transparent px-2 font-mono text-[10px] text-dim transition-colors hover:border-foreground hover:text-foreground"
            title="New folder at workspace root"
          >
            + Folder
          </button>
        </div>
      </div>

      <div className="flex-1 overflow-y-auto px-2 py-3">
        {tree.folders.map((folder) => renderFolder(folder, 0))}
        {tree.pages.length > 0 && (
          <ul className="space-y-0.5">
            {tree.pages.map((p) => (
              <li key={p.id}>{renderPage(p)}</li>
            ))}
          </ul>
        )}
        {tree.folders.length === 0 && tree.pages.length === 0 && (
          <p className="py-8 text-center text-[13px] text-muted">
            No pages yet.
            <br />
            Create one to get started.
          </p>
        )}
      </div>

      {contextMenu && (
        <div
          className="fixed z-50 min-w-[160px] overflow-hidden rounded-lg border border-border bg-surface py-1 shadow-[0_12px_30px_rgba(15,23,42,0.08),0_2px_4px_rgba(15,23,42,0.04)]"
          style={{ left: contextMenu.x, top: contextMenu.y }}
          onClick={(e) => e.stopPropagation()}
        >
          <button
            onClick={() => {
              if (contextMenu.target.type === "page") {
                onRenamePage(contextMenu.target.id, contextMenu.target.name);
              } else {
                onRenameFolder(contextMenu.target.id, contextMenu.target.name);
              }
              closeContextMenu();
            }}
            className="block w-full px-3 py-1.5 text-left text-[13px] text-foreground transition-colors hover:bg-raised"
          >
            Rename
          </button>
          {contextMenu.target.type === "folder" && (
            <>
              <button
                onClick={() => {
                  onCreatePage(contextMenu.target.id);
                  closeContextMenu();
                }}
                className="block w-full px-3 py-1.5 text-left text-[13px] text-foreground transition-colors hover:bg-raised"
              >
                New page here
              </button>
              <button
                onClick={() => {
                  onCreateFolder(contextMenu.target.id);
                  closeContextMenu();
                }}
                className="block w-full px-3 py-1.5 text-left text-[13px] text-foreground transition-colors hover:bg-raised"
              >
                New subfolder
              </button>
            </>
          )}
          {contextMenu.target.type === "page" && (() => {
            const pageTarget = contextMenu.target;
            return (
              <>
                {pageTarget.folderId && (
                  <button
                    onClick={() => {
                      onMovePage(pageTarget.id, null);
                      closeContextMenu();
                    }}
                    className="block w-full px-3 py-1.5 text-left text-[13px] text-foreground transition-colors hover:bg-raised"
                  >
                    Move to root
                  </button>
                )}
                {allFolders
                  .filter((f) => f.id !== pageTarget.folderId)
                  .map((f) => (
                    <button
                      key={f.id}
                      onClick={() => {
                        onMovePage(pageTarget.id, f.id);
                        closeContextMenu();
                      }}
                      className="block w-full truncate px-3 py-1.5 text-left text-[13px] text-foreground transition-colors hover:bg-raised"
                    >
                      Move to {f.label}
                    </button>
                  ))}
              </>
            );
          })()}
          <div className="my-1 h-px bg-border-subtle" />
          <button
            onClick={() => {
              const target = contextMenu.target;
              setShareSheet({
                x: contextMenu.x,
                y: contextMenu.y,
                objectType: target.type === "page" ? "page" : "folder",
                objectId: target.id,
                label: target.name,
              });
              closeContextMenu();
            }}
            className="block w-full px-3 py-1.5 text-left text-[13px] text-foreground transition-colors hover:bg-raised"
          >
            {contextMenu.target.type === "folder" ? (
              <>
                <span>Share folder…</span>
                <span className="ml-1 font-mono text-[10px] text-muted">applies to pages inside</span>
              </>
            ) : (
              "Share page…"
            )}
          </button>
          <div className="my-1 h-px bg-border-subtle" />
          <button
            onClick={() => {
              if (contextMenu.target.type === "page") {
                onDeletePage(contextMenu.target.id);
              } else {
                onDeleteFolder(contextMenu.target.id);
              }
              closeContextMenu();
            }}
            className="block w-full px-3 py-1.5 text-left text-[13px] text-red-500 transition-colors hover:bg-red-500/10"
          >
            Delete
          </button>
        </div>
      )}

      {shareSheet && (
        <ShareSheet
          objectType={shareSheet.objectType}
          objectId={shareSheet.objectId}
          objectLabel={shareSheet.label}
          onClose={() => setShareSheet(null)}
          anchorAt={{ x: shareSheet.x, y: shareSheet.y }}
        />
      )}
    </div>
  );
}
