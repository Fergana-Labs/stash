"use client";

import { useState } from "react";
import { PageTree, PageTreeFile, PageTreeFolder } from "../../lib/types";

interface NotebookTreeProps {
  tree: PageTree;
  selectedFileId: string | null;
  onSelectFile: (fileId: string) => void;
  onCreateFile: (folderId: string | null) => void;
  onCreateFolder: () => void;
  onDeleteFile: (fileId: string) => void;
  onDeleteFolder: (folderId: string) => void;
  onRenameFile: (fileId: string, currentName: string) => void;
  onRenameFolder: (folderId: string, currentName: string) => void;
  onMoveFile: (fileId: string, folderId: string | null) => void;
}

export default function FileTreeComponent({
  tree,
  selectedFileId,
  onSelectFile,
  onCreateFile,
  onCreateFolder,
  onDeleteFile,
  onDeleteFolder,
  onRenameFile,
  onRenameFolder,
  onMoveFile,
}: NotebookTreeProps) {
  const [collapsedFolders, setCollapsedFolders] = useState<Set<string>>(new Set());
  const [contextMenu, setContextMenu] = useState<{
    x: number;
    y: number;
    type: "file" | "folder";
    id: string;
    name: string;
    folderId?: string;
  } | null>(null);

  const toggleFolder = (folderId: string) => {
    setCollapsedFolders((prev) => {
      const next = new Set(prev);
      if (next.has(folderId)) next.delete(folderId);
      else next.add(folderId);
      return next;
    });
  };

  const handleContextMenu = (
    e: React.MouseEvent,
    type: "file" | "folder",
    id: string,
    name: string,
    folderId?: string
  ) => {
    e.preventDefault();
    setContextMenu({ x: e.clientX, y: e.clientY, type, id, name, folderId });
  };

  const closeContextMenu = () => setContextMenu(null);

  const renderFile = (file: PageTreeFile) => {
    const active = selectedFileId === file.id;
    return (
      <button
        key={file.id}
        onClick={() => onSelectFile(file.id)}
        onContextMenu={(e) =>
          handleContextMenu(e, "file", file.id, file.name, file.folder_id || undefined)
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
        <span className="truncate">{file.name}</span>
      </button>
    );
  };

  const renderFolder = (folder: PageTreeFolder) => {
    const isCollapsed = collapsedFolders.has(folder.id);
    return (
      <div key={folder.id} className="mb-4">
        <button
          onClick={() => toggleFolder(folder.id)}
          onContextMenu={(e) => handleContextMenu(e, "folder", folder.id, folder.name)}
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
          <span className="ml-auto font-mono text-[10px] text-muted">
            {folder.files.length}
          </span>
        </button>
        {!isCollapsed && (
          <ul className="mt-1 space-y-0.5">
            {folder.files.map((f) => (
              <li key={f.id}>{renderFile(f)}</li>
            ))}
            {folder.files.length === 0 && (
              <li className="px-2 py-1 text-[11px] text-muted">Empty folder</li>
            )}
          </ul>
        )}
      </div>
    );
  };

  return (
    <div className="flex h-full flex-col" onClick={closeContextMenu}>
      {/* Toolbar */}
      <div className="flex items-center justify-between gap-2 border-b border-border-subtle px-3 py-2.5">
        <p className="font-mono text-[10px] font-medium uppercase tracking-[0.12em] text-muted">
          Pages
        </p>
        <div className="flex gap-1">
          <button
            onClick={() => onCreateFile(null)}
            className="inline-flex h-6 items-center rounded border border-border bg-transparent px-2 font-mono text-[10px] text-dim transition-colors hover:border-foreground hover:text-foreground"
            title="New page"
          >
            + Page
          </button>
          <button
            onClick={onCreateFolder}
            className="inline-flex h-6 items-center rounded border border-border bg-transparent px-2 font-mono text-[10px] text-dim transition-colors hover:border-foreground hover:text-foreground"
            title="New folder"
          >
            + Folder
          </button>
        </div>
      </div>

      {/* Tree */}
      <div className="flex-1 overflow-y-auto px-2 py-3">
        {tree.folders.map(renderFolder)}
        {tree.root_files.length > 0 && (
          <ul className="space-y-0.5">
            {tree.root_files.map((f) => (
              <li key={f.id}>{renderFile(f)}</li>
            ))}
          </ul>
        )}
        {tree.folders.length === 0 && tree.root_files.length === 0 && (
          <p className="py-8 text-center text-[13px] text-muted">
            No pages yet.
            <br />
            Create one to get started.
          </p>
        )}
      </div>

      {/* Context menu */}
      {contextMenu && (
        <div
          className="fixed z-50 min-w-[160px] overflow-hidden rounded-lg border border-border bg-surface py-1 shadow-[0_12px_30px_rgba(15,23,42,0.08),0_2px_4px_rgba(15,23,42,0.04)]"
          style={{ left: contextMenu.x, top: contextMenu.y }}
          onClick={(e) => e.stopPropagation()}
        >
          <button
            onClick={() => {
              if (contextMenu.type === "file") {
                onRenameFile(contextMenu.id, contextMenu.name);
              } else {
                onRenameFolder(contextMenu.id, contextMenu.name);
              }
              closeContextMenu();
            }}
            className="block w-full px-3 py-1.5 text-left text-[13px] text-foreground transition-colors hover:bg-raised"
          >
            Rename
          </button>
          {contextMenu.type === "folder" && (
            <button
              onClick={() => {
                onCreateFile(contextMenu.id);
                closeContextMenu();
              }}
              className="block w-full px-3 py-1.5 text-left text-[13px] text-foreground transition-colors hover:bg-raised"
            >
              New page here
            </button>
          )}
          {contextMenu.type === "file" && (
            <>
              {contextMenu.folderId && (
                <button
                  onClick={() => {
                    onMoveFile(contextMenu.id, null);
                    closeContextMenu();
                  }}
                  className="block w-full px-3 py-1.5 text-left text-[13px] text-foreground transition-colors hover:bg-raised"
                >
                  Move to root
                </button>
              )}
              {tree.folders
                .filter((f: PageTreeFolder) => f.id !== contextMenu.folderId)
                .map((folder: PageTreeFolder) => (
                  <button
                    key={folder.id}
                    onClick={() => {
                      onMoveFile(contextMenu.id, folder.id);
                      closeContextMenu();
                    }}
                    className="block w-full px-3 py-1.5 text-left text-[13px] text-foreground transition-colors hover:bg-raised"
                  >
                    Move to {folder.name}
                  </button>
                ))}
            </>
          )}
          <div className="my-1 h-px bg-border-subtle" />
          <button
            onClick={() => {
              if (contextMenu.type === "file") {
                onDeleteFile(contextMenu.id);
              } else {
                onDeleteFolder(contextMenu.id);
              }
              closeContextMenu();
            }}
            className="block w-full px-3 py-1.5 text-left text-[13px] text-red-500 transition-colors hover:bg-red-500/10"
          >
            Delete
          </button>
        </div>
      )}
    </div>
  );
}
