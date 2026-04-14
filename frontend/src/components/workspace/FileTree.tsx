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
  const [expandedFolders, setExpandedFolders] = useState<Set<string>>(
    new Set(tree.folders.map((f: any) => f.id))
  );
  const [contextMenu, setContextMenu] = useState<{
    x: number;
    y: number;
    type: "file" | "folder";
    id: string;
    name: string;
    folderId?: string;
  } | null>(null);

  const toggleFolder = (folderId: string) => {
    setExpandedFolders((prev) => {
      const next = new Set(prev);
      if (next.has(folderId)) {
        next.delete(folderId);
      } else {
        next.add(folderId);
      }
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

  const renderFile = (file: PageTreeFile) => (
    <button
      key={file.id}
      onClick={() => onSelectFile(file.id)}
      onContextMenu={(e) => handleContextMenu(e, "file", file.id, file.name, file.folder_id || undefined)}
      className={`w-full text-left px-3 py-1.5 text-sm flex items-center gap-2 hover:bg-raised rounded ${
        selectedFileId === file.id ? "bg-raised text-foreground" : "text-dim"
      }`}
    >
      <svg className="w-4 h-4 text-muted flex-shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
      </svg>
      <span className="truncate">{file.name}</span>
    </button>
  );

  const renderFolder = (folder: PageTreeFolder) => {
    const isExpanded = expandedFolders.has(folder.id);
    return (
      <div key={folder.id}>
        <button
          onClick={() => toggleFolder(folder.id)}
          onContextMenu={(e) => handleContextMenu(e, "folder", folder.id, folder.name)}
          className="w-full text-left px-3 py-1.5 text-sm flex items-center gap-2 hover:bg-raised rounded text-dim"
        >
          <svg
            className={`w-4 h-4 text-muted flex-shrink-0 transition-transform ${isExpanded ? "rotate-90" : ""}`}
            fill="none"
            stroke="currentColor"
            viewBox="0 0 24 24"
          >
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
          </svg>
          <svg className="w-4 h-4 text-yellow-500 flex-shrink-0" fill="currentColor" viewBox="0 0 24 24">
            <path d="M10 4H4a2 2 0 00-2 2v12a2 2 0 002 2h16a2 2 0 002-2V8a2 2 0 00-2-2h-8l-2-2z" />
          </svg>
          <span className="truncate">{folder.name}</span>
        </button>
        {isExpanded && (
          <div className="ml-4">
            {folder.files.map(renderFile)}
            {folder.files.length === 0 && (
              <p className="text-xs text-muted px-3 py-1">Empty folder</p>
            )}
          </div>
        )}
      </div>
    );
  };

  return (
    <div className="h-full flex flex-col" onClick={closeContextMenu}>
      {/* Toolbar */}
      <div className="flex items-center gap-1 px-3 py-2 border-b border-border">
        <button
          onClick={() => onCreateFile(null)}
          className="text-xs bg-raised hover:bg-raised text-dim px-2 py-1 rounded flex items-center gap-1"
          title="New page"
        >
          <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" />
          </svg>
          Page
        </button>
        <button
          onClick={onCreateFolder}
          className="text-xs bg-raised hover:bg-raised text-dim px-2 py-1 rounded flex items-center gap-1"
          title="New folder"
        >
          <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" />
          </svg>
          Folder
        </button>
      </div>

      {/* Tree */}
      <div className="flex-1 overflow-y-auto py-1">
        {tree.folders.map(renderFolder)}
        {tree.root_files.map(renderFile)}
        {tree.folders.length === 0 && tree.root_files.length === 0 && (
          <p className="text-sm text-muted text-center py-8">
            No pages yet. Create one to get started.
          </p>
        )}
      </div>

      {/* Context menu */}
      {contextMenu && (
        <div
          className="fixed bg-raised border border-border rounded shadow-xl z-50 py-1 min-w-[140px]"
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
            className="w-full text-left px-3 py-1.5 text-sm text-dim hover:bg-raised"
          >
            Rename
          </button>
          {contextMenu.type === "folder" && (
            <button
              onClick={() => {
                onCreateFile(contextMenu.id);
                closeContextMenu();
              }}
              className="w-full text-left px-3 py-1.5 text-sm text-dim hover:bg-raised"
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
                  className="w-full text-left px-3 py-1.5 text-sm text-dim hover:bg-raised"
                >
                  Move to root
                </button>
              )}
              {tree.folders
                .filter((f: any) => f.id !== contextMenu.folderId)
                .map((folder: any) => (
                  <button
                    key={folder.id}
                    onClick={() => {
                      onMoveFile(contextMenu.id, folder.id);
                      closeContextMenu();
                    }}
                    className="w-full text-left px-3 py-1.5 text-sm text-dim hover:bg-raised"
                  >
                    Move to {folder.name}
                  </button>
                ))}
            </>
          )}
          <button
            onClick={() => {
              if (contextMenu.type === "file") {
                onDeleteFile(contextMenu.id);
              } else {
                onDeleteFolder(contextMenu.id);
              }
              closeContextMenu();
            }}
            className="w-full text-left px-3 py-1.5 text-sm text-red-400 hover:bg-raised"
          >
            Delete
          </button>
        </div>
      )}
    </div>
  );
}
