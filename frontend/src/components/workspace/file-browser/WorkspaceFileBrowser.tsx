"use client";

import { useRouter } from "next/navigation";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useEscapeKey } from "../../../hooks/useEscapeKey";
import {
  ApiError,
  createTable,
  createFolder,
  createPage,
  deleteFolder,
  deleteTable,
  getFolderContents,
  getWorkspaceTree,
  listFiles,
  listTables,
  restoreItem,
  trashItem,
  updateFile,
  updateFolder,
  updatePage,
  updateTable,
  uploadFileOrPage,
  type FolderContents,
} from "../../../lib/api";
import type {
  FolderTreeNode,
  PageSummary,
  WorkspaceTree,
} from "../../../lib/types";
import { refreshWorkspaceSidebar } from "../../../lib/skillNavigationCache";
import { useFilePins } from "../../../lib/filePins";
import { openInNewTab, type NavigateOptions } from "../../../lib/linkNavigation";
import { useWorkspaceRecents } from "../../../lib/pins";
import { FileBrowserSkeleton } from "../../SkeletonStates";
import EditableTitle from "../EditableTitle";
import FolderItemGrid from "./FolderItemGrid";
import ItemsList from "./ItemsList";
import ItemsColumns from "./ItemsColumns";
import SharedWithMeFiles from "../SharedWithMeFiles";
import QuickAccess from "./QuickAccess";
import { type GridItem, type ItemKind } from "./kind";

interface Props {
  workspaceId: string;
  folderId: string | null;
}

// Mime type carried by drag events to identify a file-browser drag. Keeps the
// browser's native file-from-OS drag (which also sets "Files") distinct from
// our own intra-app reparent drags.
export const FB_DRAG_MIME = "application/x-skill-fb-item";
// Set instead of FB_DRAG_MIME when dragging a multi-selection, so folder drop
// targets know to move every selected item at once.
export const FB_DRAG_MULTI_MIME = "application/x-skill-fb-items";

export interface FBDragPayload {
  kind: ItemKind;
  id: string;
}

type View = "list" | "column" | "grid";
// Which set of files you're looking at: your workspace's drive, or items other
// people shared with you. Only selectable at root — folders are always "mine".
type Scope = "mine" | "shared";

const VIEW_STORAGE_KEY = "stash_files_view";

export default function WorkspaceFileBrowser({ workspaceId, folderId }: Props) {
  const router = useRouter();

  const [tree, setTree] = useState<WorkspaceTree | null>(null);
  const [contents, setContents] = useState<FolderContents | null>(null);
  const [contentsLoaded, setContentsLoaded] = useState(false);
  const [rootFiles, setRootFiles] = useState<GridItem[]>([]);
  const [rootTables, setRootTables] = useState<GridItem[]>([]);
  const [allFiles, setAllFiles] = useState<GridItem[]>([]);
  const [view, setView] = useState<View>("grid");
  const [scope, setScope] = useState<Scope>("mine");
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
  const pins = useFilePins(workspaceId);
  const recents = useWorkspaceRecents(workspaceId);

  // Selection is scoped to the current listing, so reset it when the folder
  // (or workspace) changes.
  useEffect(() => {
    setSelectedIds(new Set());
  }, [folderId, workspaceId]);

  function toggleSelect(item: GridItem) {
    setSelectedIds((current) => {
      const next = new Set(current);
      if (next.has(item.id)) next.delete(item.id);
      else next.add(item.id);
      return next;
    });
  }

  function clearSelection() {
    setSelectedIds(new Set());
  }

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

  // Load workspace tree once per workspace; powers the Column view + Quick
  // Access. It's supplementary — a non-member opening a *shared* folder can't
  // read the whole tree (403), but the folder's own contents still load below,
  // so a tree failure must not surface a blocking "Not a workspace member" error.
  const loadTree = useCallback(async () => {
    try {
      const t = await getWorkspaceTree(workspaceId);
      setTree(t);
    } catch (e) {
      if (e instanceof ApiError && e.status === 403) return;
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
        setRootTables([]);
      } catch (e) {
        setError(e instanceof Error ? e.message : "Failed to load folder");
      } finally {
        setContentsLoaded(true);
      }
    } else {
      try {
        const [t, allFiles, tablesResp] = await Promise.all([
          getWorkspaceTree(workspaceId),
          listFiles(workspaceId),
          listTables(workspaceId),
        ]);
        setTree(t);
        setContents(null);
        setAllFiles(allFiles.map((f) => fileToGridItem(f)));
        setRootFiles(
          allFiles.filter((f) => !f.folder_id).map((f) => fileToGridItem(f)),
        );
        const linkedTableIds = new Set(
          allFiles
            .map((file) => file.linked_table_id)
            .filter((tableId): tableId is string => !!tableId)
        );
        setRootTables(
          tablesResp.tables
            .filter((t) => !t.folder_id && !linkedTableIds.has(t.id))
            .map((t) => tableToGridItem(t)),
        );
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
      ...rootTables,
    ];
  }, [tree, rootFiles, rootTables]);

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
        ...contents.tables.map((t) => tableToGridItem(t)),
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
      ...rootTables,
    ];
  }, [folderId, contents, tree, rootFiles, rootTables]);

  // Every folder/page/file in the workspace, flattened, so Pinned + Recent can
  // resolve and surface items that live anywhere — not just at the root.
  const allItems: GridItem[] = useMemo(() => {
    if (!tree) return [];
    const folders = flattenFolders(tree.folders);
    const pages = [
      ...tree.pages,
      ...folders.flatMap((f) => f.pages ?? []),
    ];
    return [
      ...folders.map((sub) => ({
        kind: "folder" as const,
        id: sub.id,
        name: sub.name,
        subtitle: subtitleForFolder(sub.pages?.length ?? 0, 0),
        updatedAt: sub.updated_at,
      })),
      ...pages.map((p) => pageToGridItem(p)),
      ...allFiles,
    ];
  }, [tree, allFiles]);

  const itemById = useMemo(() => {
    const map = new Map<string, GridItem>();
    for (const item of allItems) map.set(item.id, item);
    return map;
  }, [allItems]);

  const pinnedItems = useMemo(
    () =>
      pins.pinnedIds
        .map((id) => itemById.get(id))
        .filter((item): item is GridItem => !!item),
    [pins.pinnedIds, itemById],
  );

  // Recent is per-user: the server returns this user's recently-viewed object
  // ids (most-recent first); we resolve them to items, drop pinned ones, and
  // cap the strip. Items that aren't files (or are gone) simply don't resolve.
  const recentItems = useMemo(() => {
    return recents
      .map((entry) => itemById.get(entry.object_id))
      .filter((item): item is GridItem => !!item && !pins.pinnedSet.has(item.id))
      .slice(0, 8);
  }, [recents, itemById, pins.pinnedSet]);

  const loadingItems = folderId ? contents === null : !contentsLoaded;

  async function refreshAll() {
    await Promise.all([loadTree(), loadContents()]);
  }

  // Move a single folder/page/file into the target folder (or root when
  // targetFolderId === null). No refresh — callers batch that.
  async function moveOne(payload: FBDragPayload, targetFolderId: string | null) {
    if (payload.kind === "folder" && payload.id === targetFolderId) return;
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
    } else if (payload.kind === "datatable") {
      // Standalone tables live in their own `tables` table.
      await updateTable(
        workspaceId,
        payload.id,
        targetFolderId === null
          ? { move_to_root: true }
          : { folder_id: targetFolderId }
      );
    } else {
      // A "table" item here is a CSV file linked to a table — it lives in the
      // files table, so it moves like any other file.
      await updateFile(
        workspaceId,
        payload.id,
        targetFolderId === null
          ? { move_to_root: true }
          : { folder_id: targetFolderId }
      );
    }
  }

  async function reparent(payload: FBDragPayload, targetFolderId: string | null) {
    try {
      await moveOne(payload, targetFolderId);
      await refreshAll();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Move failed");
    }
  }

  // Move every dragged item into the target folder, then refresh once.
  async function reparentMany(payloads: FBDragPayload[], targetFolderId: string | null) {
    try {
      for (const payload of payloads) await moveOne(payload, targetFolderId);
      await refreshAll();
      clearSelection();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Move failed");
    }
  }

  function hrefForItem(item: GridItem): string {
    if (item.kind === "folder") {
      return `/workspaces/${workspaceId}/folders/${item.id}`;
    }
    if (item.kind === "page" || item.kind === "html") {
      return `/p/${item.id}`;
    }
    if (item.kind === "datatable") {
      return `/tables/${item.id}`;
    }
    if (item.kind === "table" && item.linkedTableId) {
      return `/tables/${item.linkedTableId}`;
    }
    return `/f/${item.id}`;
  }

  function navigateTo(item: GridItem, options?: NavigateOptions) {
    const href = hrefForItem(item);
    if (options?.newTab) {
      openInNewTab(href);
      return;
    }
    router.push(href);
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
          router.push(`/p/${result.page.id}`);
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
      refreshWorkspaceSidebar(workspaceId).catch(() => {});
      router.push(`/p/${p.id}`);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to create page");
    }
  }

  async function handleNewTable() {
    try {
      const table = await createTable(workspaceId, "Untitled table");
      // createTable has no folder param, so move the new table into the
      // current folder before navigating.
      if (folderId) {
        await updateTable(workspaceId, table.id, { folder_id: folderId });
      }
      refreshWorkspaceSidebar(workspaceId).catch(() => {});
      router.push(`/tables/${table.id}`);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to create table");
    }
  }

  async function handleNewFolder() {
    const name = window.prompt("Folder name?");
    if (!name?.trim()) return;
    try {
      await createFolder(workspaceId, name.trim(), folderId ?? undefined);
      await refreshAll();
      refreshWorkspaceSidebar(workspaceId).catch(() => {});
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
    if (item.kind === "datatable") {
      // Standalone tables have no trash — hard delete behind a confirm.
      const yes = window.confirm(`Delete table "${item.name}"? This can't be undone.`);
      if (!yes) return;
      try {
        await deleteTable(workspaceId, item.id);
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

  // Bulk delete the current selection after one confirm. Folders and
  // standalone tables are hard deletes; pages/files go to trash.
  async function bulkDelete(targets: GridItem[]) {
    if (targets.length === 0) return;
    const hasFolder = targets.some((t) => t.kind === "folder");
    const detail = hasFolder
      ? " Folders are deleted permanently."
      : "";
    const yes = window.confirm(
      `Delete ${targets.length} item${targets.length === 1 ? "" : "s"}?${detail}`
    );
    if (!yes) return;
    try {
      for (const item of targets) {
        if (item.kind === "folder") {
          await deleteFolder(workspaceId, item.id);
        } else if (item.kind === "datatable") {
          await deleteTable(workspaceId, item.id);
        } else {
          const kind = item.kind === "page" || item.kind === "html" ? "page" : "file";
          await trashItem(workspaceId, kind, item.id);
        }
      }
      await refreshAll();
      clearSelection();
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
    kind: "folder" | "page" | "html" | "table" | "datatable" | "file",
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
    if (kind === "datatable") {
      const updated = await updateTable(workspaceId, id, { name: next });
      await refreshAll();
      return updated.name;
    }
    const updated = await updateFile(workspaceId, id, { name: next });
    await refreshAll();
    return updated.name;
  }

  if (loadingItems && !error) return <FileBrowserSkeleton />;

  const showQuickAccess =
    !folderId &&
    view !== "column" &&
    (pinnedItems.length > 0 || recentItems.length > 0);

  const selectedItems = items.filter((item) => selectedIds.has(item.id));
  const selectedDragPayloads: FBDragPayload[] = selectedItems
    .filter((item) => item.movable !== false)
    .map((item) => ({
      kind: item.kind,
      id: item.id,
    }));

  const showShared = !folderId && scope === "shared";

  return (
    <div className="scroll-thin flex-1 overflow-y-auto">
      <div className="mx-auto max-w-5xl px-8 py-7">
        {!folderId && <ScopeTabs scope={scope} onChange={setScope} />}
        {/* Header: the page path lives in AppShell's top-bar breadcrumb, so we
            only show the current folder name (rename target) or the section
            title here, alongside the view toggle + create actions. */}
        {!showShared && (
          <div className="mt-4 flex flex-wrap items-center justify-between gap-3">
            {folderId && contents?.folder ? (
              <h1 className="m-0 min-w-0 font-display text-[22px] font-semibold leading-tight tracking-tight text-foreground">
                <EditableTitle
                  value={contents.folder.name}
                  onSave={(next) => renameItem("folder", folderId, next)}
                />
              </h1>
            ) : (
              // Root: the breadcrumb + sidebar already say "Files"; no redundant title.
              <div />
            )}
            <div className="flex flex-wrap items-center gap-2">
              <ViewToggle view={view} onChange={setViewPersisted} />
              <button
                type="button"
                onClick={handleUploadFile}
                className="rounded-md border border-border bg-base px-2.5 py-1 text-[12px] font-medium text-foreground hover:bg-raised"
              >
                + Upload
              </button>
              <NewMenu
                onNewFolder={handleNewFolder}
                onNewPage={handleNewPage}
                onNewTable={handleNewTable}
              />
            </div>
          </div>
        )}

        {error && (
          <div className="mt-4 rounded-lg border border-red-300/40 bg-red-500/10 px-4 py-2 text-[13px] text-red-500">
            {error}
          </div>
        )}

        {showShared ? (
          <div className="mt-5">
            <SharedWithMeFiles />
          </div>
        ) : (
          <>
            {showQuickAccess && (
              <QuickAccess
                pinned={pinnedItems}
                recent={recentItems}
                onOpen={navigateTo}
                isPinned={(item) => pins.isPinned(item.id)}
                onTogglePin={(item) => pins.toggle(item.id)}
                onReparent={reparent}
                onReparentMany={reparentMany}
              />
            )}

            <div className={view === "column" ? "mt-5 h-[68vh]" : "mt-5"}>
              {view === "list" && (
                <ItemsList
                  items={items}
                  onNavigate={navigateTo}
                  onReparent={reparent}
                  onReparentMany={reparentMany}
                  onDelete={handleDelete}
                  isPinned={(item) => pins.isPinned(item.id)}
                  onTogglePin={(item) => pins.toggle(item.id)}
                  selectedIds={selectedIds}
                  onToggleSelect={toggleSelect}
                  selectedDragPayloads={selectedDragPayloads}
                />
              )}
              {view === "grid" && (
                <FolderItemGrid
                  items={items}
                  selectedId={null}
                  onSelect={navigateTo}
                  onNavigate={navigateTo}
                  onReparent={reparent}
                  onReparentMany={reparentMany}
                  onDelete={handleDelete}
                  selectedIds={selectedIds}
                  onToggleSelect={toggleSelect}
                  selectedDragPayloads={selectedDragPayloads}
                />
              )}
              {view === "column" && (
                <ItemsColumns
                  workspaceId={workspaceId}
                  rootItems={rootItems}
                  onNavigate={navigateTo}
                  onReparent={reparent}
                  onDelete={handleDelete}
                />
              )}
            </div>
          </>
        )}
      </div>
      {selectedItems.length > 0 && (
        <div className="pointer-events-none fixed inset-x-0 bottom-6 z-50 flex justify-center">
          <div className="pointer-events-auto flex items-center gap-3 rounded-lg border border-border bg-foreground px-4 py-2 text-[13px] text-background shadow-lg">
            <span className="font-medium">
              {selectedItems.length} selected
            </span>
            <span className="hidden text-[11.5px] text-background/60 sm:inline">
              drag onto a folder to move
            </span>
            <button
              type="button"
              onClick={() => void bulkDelete(selectedItems)}
              className="rounded-md border border-background/40 px-2 py-0.5 text-[12px] font-semibold hover:bg-background/10"
            >
              Delete
            </button>
            <button
              type="button"
              onClick={clearSelection}
              className="ml-1 text-[18px] leading-none text-background/70 hover:text-background"
              aria-label="Clear selection"
            >
              ×
            </button>
          </div>
        </div>
      )}
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

// Drive-style root selector: your workspace's files vs items shared with you.
function ScopeTabs({ scope, onChange }: { scope: Scope; onChange: (next: Scope) => void }) {
  const tabs: { key: Scope; label: string }[] = [
    { key: "mine", label: "My files" },
    { key: "shared", label: "Shared with me" },
  ];
  return (
    <div className="flex gap-1 border-b border-border">
      {tabs.map((t) => {
        const active = scope === t.key;
        return (
          <button
            key={t.key}
            type="button"
            onClick={() => onChange(t.key)}
            className={
              "-mb-px border-b-2 px-3 py-2 text-[13px] transition-colors " +
              (active
                ? "border-[var(--color-brand-600)] font-semibold text-foreground"
                : "border-transparent text-muted hover:text-foreground")
            }
          >
            {t.label}
          </button>
        );
      })}
    </div>
  );
}

// One "+ New" button for everything creatable here (Drive-style), so the
// toolbar stays two buttons no matter how many creatable kinds we grow.
function NewMenu({
  onNewFolder,
  onNewPage,
  onNewTable,
}: {
  onNewFolder: () => void;
  onNewPage: () => void;
  onNewTable: () => void;
}) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  useEscapeKey(open, () => setOpen(false));

  useEffect(() => {
    if (!open) return;
    const onDown = (e: MouseEvent) => {
      if (!ref.current?.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", onDown);
    return () => document.removeEventListener("mousedown", onDown);
  }, [open]);

  const options: { label: string; onSelect: () => void }[] = [
    { label: "Folder", onSelect: onNewFolder },
    { label: "Page", onSelect: onNewPage },
    { label: "Table", onSelect: onNewTable },
  ];

  return (
    <div ref={ref} className="relative inline-block">
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        aria-haspopup="menu"
        aria-expanded={open}
        className="rounded-md border border-border bg-base px-2.5 py-1 text-[12px] font-medium text-foreground hover:bg-raised"
      >
        + New <span aria-hidden className="text-[10px]">▾</span>
      </button>
      {open && (
        <div className="absolute right-0 top-full z-30 mt-1 w-44 overflow-hidden rounded-md border border-border bg-surface py-1 text-[12.5px] shadow-lg">
          {options.map((o) => (
            <button
              key={o.label}
              type="button"
              onClick={() => {
                setOpen(false);
                o.onSelect();
              }}
              className="block w-full px-3 py-1.5 text-left text-foreground hover:bg-raised"
            >
              {o.label}
            </button>
          ))}
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

function tableToGridItem(table: { id: string; name: string; row_count: number | null }): GridItem {
  const rows = table.row_count ?? 0;
  return {
    kind: "datatable",
    id: table.id,
    name: table.name,
    subtitle: `table · ${rows} row${rows === 1 ? "" : "s"}`,
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

function flattenFolders(folders: FolderTreeNode[]): FolderTreeNode[] {
  return folders.flatMap((folder) => [folder, ...flattenFolders(folder.folders ?? [])]);
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
