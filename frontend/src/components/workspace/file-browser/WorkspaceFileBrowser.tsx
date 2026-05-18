"use client";

import { useRouter } from "next/navigation";
import { useCallback, useEffect, useMemo, useState } from "react";
import {
  createFolder,
  createPage,
  deleteFile,
  deletePage,
  deleteFolder,
  getFolderContents,
  getWorkspaceTree,
  listFiles,
  updateFile,
  updateFolder,
  updatePage,
  uploadFile,
  type FolderContents,
} from "../../../lib/api";
import type {
  FolderTreeNode,
  PageSummary,
  WorkspaceTree,
} from "../../../lib/types";
import FolderTreePane from "./FolderTreePane";
import FolderItemGrid, { type GridItem, type ItemKind } from "./FolderItemGrid";
import ItemPreviewPane, { type PreviewSelection } from "./ItemPreviewPane";

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

export default function WorkspaceFileBrowser({ workspaceId, folderId }: Props) {
  const router = useRouter();

  const [tree, setTree] = useState<WorkspaceTree | null>(null);
  const [contents, setContents] = useState<FolderContents | null>(null);
  const [rootFiles, setRootFiles] = useState<GridItem[]>([]);
  const [selected, setSelected] = useState<PreviewSelection | null>(null);
  const [error, setError] = useState("");

  // Load workspace tree once per workspace; it powers the left rail.
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
    setSelected(null);
    if (folderId) {
      try {
        const c = await getFolderContents(workspaceId, folderId);
        setContents(c);
        setRootFiles([]);
      } catch (e) {
        setError(e instanceof Error ? e.message : "Failed to load folder");
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
      }
    }
  }, [workspaceId, folderId]);

  useEffect(() => {
    loadTree();
  }, [loadTree]);

  useEffect(() => {
    loadContents();
  }, [loadContents]);

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
        ...contents.pages.map((p) => ({
          kind: "page" as const,
          id: p.id,
          name: p.name.replace(/\.md$/, ""),
          subtitle: p.name.toLowerCase().endsWith(".html") ? "html page" : "page",
        })),
        ...contents.files.map((f) =>
          fileToGridItem({
            id: f.id,
            name: f.name,
            content_type: f.content_type,
            size_bytes: f.size_bytes,
            linked_table_id: f.linked_table_id ?? null,
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
      })),
      ...tree.pages.map((p: PageSummary) => ({
        kind: "page" as const,
        id: p.id,
        name: p.name.replace(/\.md$/, ""),
        subtitle: p.name.toLowerCase().endsWith(".html") ? "html page" : "page",
      })),
      ...rootFiles,
    ];
  }, [folderId, contents, tree, rootFiles]);

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
        await uploadFile(workspaceId, file, folderId ?? undefined);
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

  async function handleDelete(item: PreviewSelection) {
    const yes = window.confirm(`Delete "${item.name}"? This can't be undone.`);
    if (!yes) return;
    try {
      if (item.kind === "folder") await deleteFolder(workspaceId, item.id);
      else if (item.kind === "page" || item.kind === "html") await deletePage(workspaceId, item.id);
      else await deleteFile(workspaceId, item.id);
      setSelected(null);
      await refreshAll();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Delete failed");
    }
  }

  return (
    <div className="flex h-full min-h-0 flex-col">
      {/* Top strip — toolbar only. The page path is already shown in
          AppShell's breadcrumb, so an in-page breadcrumb would just
          duplicate it. */}
      <div className="flex flex-wrap items-center justify-end gap-1.5 border-b border-border bg-surface px-4 py-2.5">
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

      {/* Three-pane Drive shape */}
      <div className="grid min-h-0 flex-1 grid-cols-[220px_minmax(0,1fr)_280px] divide-x divide-border">
        <FolderTreePane
          workspaceId={workspaceId}
          tree={tree}
          activeFolderId={folderId}
          onReparent={reparent}
        />
        <FolderItemGrid
          items={items}
          selectedId={selected?.id ?? null}
          onSelect={(item) =>
            setSelected({
              kind: item.kind,
              id: item.id,
              name: item.name,
              subtitle: item.subtitle,
              sizeBytes: item.sizeBytes,
              linkedTableId: item.linkedTableId,
            })
          }
          onNavigate={navigateTo}
          onReparent={reparent}
        />
        <ItemPreviewPane
          workspaceId={workspaceId}
          selection={selected}
          onOpen={(s) => navigateTo(gridFromPreview(s))}
          onDelete={handleDelete}
        />
      </div>
    </div>
  );
}

function fileToGridItem(file: {
  id: string;
  name: string;
  content_type: string;
  size_bytes: number;
  linked_table_id?: string | null;
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

function gridFromPreview(s: PreviewSelection): GridItem {
  return {
    kind: s.kind,
    id: s.id,
    name: s.name,
    subtitle: s.subtitle,
    sizeBytes: s.sizeBytes,
    linkedTableId: s.linkedTableId,
  };
}

// Re-export tree node type for callers that want it.
export type { FolderTreeNode };