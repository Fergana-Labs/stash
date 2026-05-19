"use client";

import { useRouter } from "next/navigation";
import { useCallback, useEffect, useMemo, useState } from "react";
import {
  createFolder,
  createPage,
  deleteFolder,
  getFolderContents,
  getWorkspaceTree,
  listFiles,
  restoreItem,
  trashItem,
  updateFile,
  updateFolder,
  updatePage,
  uploadFileOrPage,
  type FolderContents,
} from "../../../lib/api";
import type {
  FolderTreeNode,
  PageSummary,
  WorkspaceTree,
} from "../../../lib/types";
import { FileBrowserSkeleton } from "../../SkeletonStates";
import EditableTitle from "../EditableTitle";
import FolderItemGrid, { type GridItem, type ItemKind } from "./FolderItemGrid";
import ItemsList from "./ItemsList";
import ItemsColumns from "./ItemsColumns";

interface Props {
  workspaceId: string;
  folderId: string | null;
}

// Mime type carried by drag events to identify a file-browser drag. Keeps the
// browser's native file-from-OS drag (which also sets "Files") distinct from
// our own intra-app reparent drags.
export const FB_DRAG_MIME = "application/x-stash-fb-item";

export interface FBDragPayload {
  kind: ItemKind;
  id: string;
}

type View = "list" | "column" | "grid";

const VIEW_STORAGE_KEY = "stash_files_view";

export default function WorkspaceFileBrowser({ workspaceId, folderId }: Props) {
  const router = useRouter();

  const [tree, setTree] = useState<WorkspaceTree | null>(null);
  const [contents, setContents] = useState<FolderContents | null>(null);
  const [contentsLoaded, setContentsLoaded] = useState(false);
  const [rootFiles, setRootFiles] = useState<GridItem[]>([]);
  const [view, setView] = useState<View>("grid");

  // Restore last-used view from localStorage on mount.
  useEffect(() => {
    if (typeof window === "undefined") return;
    const saved = window.localStorage.getItem(VIEW_STORAGE_KEY) as View | null;
    if (saved === "list" || saved === "column" || saved === "grid") setView(saved);
  }, []);

  function setViewPersisted(next: View) {
    setView(next);
    try {
      window.localStorage.setItem(VIEW_STORAGE_KEY, next);
    } catch {
      /* ignore */
    }
  }
  const [error, setError] = useState("");
  const [undo, setUndo] = useState<{ kind: "page" | "file"; id: string; name: string } | null>(
    null,
  );

  // Auto-dismiss the Undo toast after 10s. Matches the gmail-style window.
  useEffect(() => {
    if (!undo) return;
    const t = window.setTimeout(() => setUndo(null), 10000);
    return () => window.clearTimeout(t);
  }, [undo]);

  // Load workspace tree once per workspace; powers the Column view.
  const loadTree = useCallback(async () => {
    try {
      const t = await getWorkspaceTree(workspaceId);
      setTree(t);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load workspace");
    }
  }, [workspaceId]);

  // Load whatever is in the center grid right now. For a real folder this is
  // /folders/{id}/contents. For the root view there's no such endpoint, so we
  // synthesize the contents from the tree + a list-files call.
  const loadContents = useCallback(async () => {
    setContentsLoaded(false);
    if (folderId) {
      try {
        const c = await getFolderContents(workspaceId, folderId);
        setContents(c);
        setRootFiles([]);
      } catch (e) {
        setError(e instanceof Error ? e.message : "Failed to load folder");
      } finally {
        setContentsLoaded(true);
      }
    } else {
      try {
        const [t, allFiles] = await Promise.all([
          getWorkspaceTree(workspaceId),
          listFiles(workspaceId),
        ]);
        setTree(t);
        setContents(null);
        const roots = allFiles
          .filter((f) => !f.folder_id)
          .map((f) => fileToGridItem(f));
        setRootFiles(roots);
      } catch (e) {
        setError(e instanceof Error ? e.message : "Failed to load root");
      } finally {
        setContentsLoaded(true);
      }
    }
  }, [workspaceId, folderId]);

  useEffect(() => {
    loadTree();
  }, [loadTree]);

  useEffect(() => {
    loadContents();
  }, [loadContents]);

  // Always-root projection of folders + pages + rootFiles. The Column view
  // manages its own drill state, so it needs root regardless of the current
  // folderId.
  const rootItems: GridItem[] = useMemo(() => {
    if (!tree) return [];
    return [
      ...tree.folders.map((sub) => ({
        kind: "folder" as const,
        id: sub.id,
        name: sub.name,
        subtitle: subtitleForFolder(sub.pages?.length ?? 0, 0),
        updatedAt: sub.updated_at,
      })),
      ...tree.pages.map((p: PageSummary) => pageToGridItem(p)),
      ...rootFiles,
    ];
  }, [tree, rootFiles]);

  const items: GridItem[] = useMemo(() => {
    if (folderId) {
      if (!contents) return [];
      return [
        ...contents.subfolders.map((sub) => ({
          kind: "folder" as const,
          id: sub.id,
          name: sub.name,
          subtitle: subtitleForFolder(sub.page_count, sub.file_count),
        })),
        ...contents.pages.map((p) => pageToGridItem(p)),
        ...contents.files.map((f) =>
          fileToGridItem({
            id: f.id,
            name: f.name,
            content_type: f.content_type,
            size_bytes: f.size_bytes,
            linked_table_id: f.linked_table_id ?? null,
            created_at: f.created_at,
          })
        ),
      ];
    }
    if (!tree) return [];
    return [
      ...tree.folders.map((sub) => ({
        kind: "folder" as const,
        id: sub.id,
        name: sub.name,
        subtitle: subtitleForFolder(
          sub.pages?.length ?? 0,
          // file count isn't returned in the tree; approximate as 0
          0
        ),
        updatedAt: sub.updated_at,
      })),
      ...tree.pages.map((p: PageSummary) => pageToGridItem(p)),
      ...rootFiles,
    ];
  }, [folderId, contents, tree, rootFiles]);

  const loadingItems = folderId ? contents === null : !contentsLoaded;

  async function refreshAll() {
    await Promise.all([loadTree(), loadContents()]);
  }

  // Reparent: move a folder/page/file into the target folder (or root when
  // targetFolderId === null). Skips work when target == current parent.
  async function reparent(payload: FBDragPayload, targetFolderId: string | null) {
    try {
      if (payload.kind === "folder") {
        await updateFolder(
          workspaceId,
          payload.id,
          targetFolderId === null
            ? { move_to_root: true }
            : { parent_folder_id: targetFolderId }
        );
      } else if (payload.kind === "page" || payload.kind === "html") {
        await updatePage(
          workspaceId,
          payload.id,
          targetFolderId === null
            ? { move_to_root: true }
            : { folder_id: targetFolderId }
        );
      } else {
        // table + file both live in the files table at the data layer.
        await updateFile(
          workspaceId,
          payload.id,
          targetFolderId === null
            ? { move_to_root: true }
            : { folder_id: targetFolderId }
        );
      }
      await refreshAll();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Move failed");
    }
  }

  function navigateTo(item: GridItem) {
    if (item.kind === "folder") {
      router.push(`/workspaces/${workspaceId}/folders/${item.id}`);
    } else if (item.kind === "page" || item.kind === "html") {
      router.push(`/workspaces/${workspaceId}/p/${item.id}`);
    } else if (item.kind === "table" && item.linkedTableId) {
      router.push(`/tables/${item.linkedTableId}?workspaceId=${workspaceId}`);
    } else {
      router.push(`/workspaces/${workspaceId}/f/${item.id}`);
    }
  }

  async function handleUploadFile() {
    const input = document.createElement("input");
    input.type = "file";
    input.onchange = async () => {
      const file = input.files?.[0];
      if (!file) return;
      try {
        const result = await uploadFileOrPage(workspaceId, file, folderId ?? undefined);
        if (result.kind === "page") {
          router.push(`/workspaces/${workspaceId}/p/${result.page.id}`);
          return;
        }
        await refreshAll();
      } catch (e) {
        setError(e instanceof Error ? e.message : "Upload failed");
      }
    };
    input.click();
  }

  async function handleNewPage() {
    try {
      const p = await createPage(workspaceId, "Untitled", folderId ?? undefined);
      router.push(`/workspaces/${workspaceId}/p/${p.id}`);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to create page");
    }
  }

  async function handleNewFolder() {
    const name = window.prompt("Folder name?");
    if (!name?.trim()) return;
    try {
      await createFolder(workspaceId, name.trim(), folderId ?? undefined);
      await refreshAll();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to create folder");
    }
  }

  async function handleDelete(item: GridItem) {
    if (item.kind === "folder") {
      const yes = window.confirm(`Delete folder "${item.name}"? This can't be undone.`);
      if (!yes) return;
      try {
        await deleteFolder(workspaceId, item.id);
        await refreshAll();
      } catch (e) {
        setError(e instanceof Error ? e.message : "Delete failed");
      }
      return;
    }
    const kind = item.kind === "page" || item.kind === "html" ? "page" : "file";
    try {
      await trashItem(workspaceId, kind, item.id);
      await refreshAll();
      setUndo({ kind, id: item.id, name: item.name });
    } catch (e) {
      setError(e instanceof Error ? e.message : "Delete failed");
    }
  }

  async function handleUndoDelete() {
    if (!undo) return;
    const { kind, id } = undo;
    setUndo(null);
    try {
      await restoreItem(workspaceId, kind, id);
      await refreshAll();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Restore failed");
    }
  }

  // Rename callback used by the folder strip + per-item context menus.
  // Dispatches by kind since each lives in its own table with its own API.
  async function renameItem(
    kind: "folder" | "page" | "html" | "table" | "file",
    id: string,
    next: string
  ): Promise<string> {
    if (kind === "folder") {
      const updated = await updateFolder(workspaceId, id, { name: next });
      await refreshAll();
      return updated.name;
    }
    if (kind === "page" || kind === "html") {
      const updated = await updatePage(workspaceId, id, { name: next });
      await refreshAll();
      return updated.name;
    }
    const updated = await updateFile(workspaceId, id, { name: next });
    await refreshAll();
    return updated.name;
  }

  if (loadingItems && !error) return <FileBrowserSkeleton />;

  return (
    <div className="flex h-full min-h-0 flex-col">
      {/* Top strip: current folder name (rename target) + toolbar. The page
          path is shown in AppShell's top-bar breadcrumb, so we only repeat
          the *current* folder here as an inline-editable title. */}
      <div className="flex flex-wrap items-center gap-3 border-b border-border bg-surface px-4 py-2.5">
        {folderId && contents?.folder ? (
          <h2 className="m-0 min-w-0 font-display text-[15px] font-semibold leading-tight text-foreground">
            <EditableTitle
              value={contents.folder.name}
              onSave={(next) => renameItem("folder", folderId, next)}
            />
          </h2>
        ) : (
          <span className="text-[12.5px] font-medium text-muted">Files</span>
        )}
        <span className="flex-1" />
        <ViewToggle view={view} onChange={setViewPersisted} />
        <button
          type="button"
          onClick={handleUploadFile}
          className="rounded-md border border-border bg-base px-2.5 py-1 text-[12px] font-medium text-foreground hover:bg-raised"
        >
          + Upload
        </button>
        <button
          type="button"
          onClick={handleNewPage}
          className="rounded-md border border-border bg-base px-2.5 py-1 text-[12px] font-medium text-foreground hover:bg-raised"
        >
          + New page
        </button>
        <button
          type="button"
          onClick={handleNewFolder}
          className="rounded-md border border-border bg-base px-2.5 py-1 text-[12px] font-medium text-foreground hover:bg-raised"
        >
          + New folder
        </button>
      </div>

      {error && (
        <div className="border-b border-red-200 bg-red-50 px-4 py-2 text-[12px] text-red-700">
          {error}
        </div>
      )}

      <div className="flex min-h-0 flex-1 flex-col">
        {view === "list" && (
          <ItemsList
            items={items}
            onNavigate={navigateTo}
            onReparent={reparent}
            onDelete={handleDelete}
          />
        )}
        {view === "grid" && (
          <FolderItemGrid
            items={items}
            selectedId={null}
            onSelect={navigateTo}
            onNavigate={navigateTo}
            onReparent={reparent}
            onDelete={handleDelete}
          />
        )}
        {view === "column" && (
          <ItemsColumns
            workspaceId={workspaceId}
            tree={tree}
            rootItems={rootItems}
            onNavigate={navigateTo}
            onReparent={reparent}
            onDelete={handleDelete}
          />
        )}
      </div>
      {undo && (
        <div className="pointer-events-none fixed inset-x-0 bottom-6 z-50 flex justify-center">
          <div className="pointer-events-auto flex items-center gap-3 rounded-lg border border-border bg-foreground px-4 py-2 text-[13px] text-background shadow-lg">
            <span>Moved &ldquo;{undo.name}&rdquo; to trash.</span>
            <button
              type="button"
              onClick={handleUndoDelete}
              className="rounded-md border border-background/40 px-2 py-0.5 text-[12px] font-semibold hover:bg-background/10"
            >
              Undo
            </button>
            <button
              type="button"
              onClick={() => setUndo(null)}
              className="ml-1 text-[18px] leading-none text-background/70 hover:text-background"
              aria-label="Dismiss"
            >
              ×
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

function ViewToggle({ view, onChange }: { view: View; onChange: (next: View) => void }) {
  const opts: { key: View; label: string }[] = [
    { key: "list", label: "List" },
    { key: "column", label: "Column" },
    { key: "grid", label: "Grid" },
  ];
  return (
    <div className="inline-flex gap-0.5 rounded-md border border-border bg-base p-[2px] text-[12px]">
      {opts.map((opt) => {
        const active = view === opt.key;
        return (
          <button
            key={opt.key}
            type="button"
            onClick={() => onChange(opt.key)}
            className={
              "rounded px-2 py-[3px] " +
              (active ? "bg-raised font-semibold text-foreground" : "text-muted hover:text-foreground")
            }
          >
            {opt.label}
          </button>
        );
      })}
    </div>
  );
}

function fileToGridItem(file: {
  id: string;
  name: string;
  content_type: string;
  size_bytes: number;
  linked_table_id?: string | null;
  created_at?: string;
}): GridItem {
  const isCsvLinked = !!(file.content_type.includes("csv") && file.linked_table_id);
  return {
    kind: isCsvLinked ? "table" : "file",
    id: file.id,
    name: file.name,
    subtitle: `${file.content_type || "file"} · ${formatBytes(file.size_bytes)}`,
    sizeBytes: file.size_bytes,
    linkedTableId: file.linked_table_id ?? undefined,
    contentType: file.content_type,
    updatedAt: file.created_at,
  };
}

function pageToGridItem(page: {
  id: string;
  name: string;
  content_type: "markdown" | "html";
  updated_at?: string;
}): GridItem {
  const isHtml = page.content_type === "html";
  return {
    kind: isHtml ? "html" : "page",
    id: page.id,
    name: page.name.replace(/\.md$/, ""),
    subtitle: isHtml ? "html page" : "page",
    updatedAt: page.updated_at,
  };
}

function subtitleForFolder(pages: number, files: number): string {
  const parts: string[] = [];
  if (pages) parts.push(`${pages} page${pages === 1 ? "" : "s"}`);
  if (files) parts.push(`${files} file${files === 1 ? "" : "s"}`);
  return parts.join(" · ") || "Empty";
}

function formatBytes(b: number): string {
  if (!b) return "0 B";
  if (b < 1024) return `${b} B`;
  if (b < 1024 * 1024) return `${(b / 1024).toFixed(1)} KB`;
  return `${(b / 1024 / 1024).toFixed(1)} MB`;
}

// Re-export tree node type for callers that want it.
export type { FolderTreeNode };
