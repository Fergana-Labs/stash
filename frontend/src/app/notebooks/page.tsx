"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import AppShell from "../../components/AppShell";
import NotebookTreeComponent from "../../components/workspace/FileTree";
import MarkdownEditor from "../../components/workspace/MarkdownEditor";
import { useAuth } from "../../hooks/useAuth";
import {
  listAllNotebooks,
  createPersonalNotebook,
  deletePersonalNotebook,
  listPersonalPageTree,
  listPageTree,
  createPersonalPage,
  createPage,
  getPersonalPage,
  getPage,
  updatePersonalPage,
  updatePage,
  deletePersonalPage,
  deletePage,
  createPersonalPageFolder,
  createPageFolder,
  renamePersonalPageFolder,
  renamePageFolder,
  deletePersonalPageFolder,
  deletePageFolder,
} from "../../lib/api";
import { Notebook, NotebookPage, NotebookWithWorkspace, PageTree } from "../../lib/types";

export default function NotebooksPage() {
  const router = useRouter();
  const { user, loading, logout } = useAuth();
  const [notebooks, setNotebooks] = useState<NotebookWithWorkspace[]>([]);
  const [selectedNotebook, setSelectedNotebook] = useState<NotebookWithWorkspace | null>(null);
  const [tree, setTree] = useState<PageTree>({ folders: [], root_files: [] });
  const [selectedPageId, setSelectedPageId] = useState<string | null>(null);
  const [selectedPage, setSelectedPage] = useState<NotebookPage | null>(null);
  const [error, setError] = useState("");

  const loadNotebooks = useCallback(async () => {
    try {
      const res = await listAllNotebooks();
      setNotebooks(res?.notebooks ?? []);
    } catch { /* ignore */ }
  }, []);

  useEffect(() => { if (user) loadNotebooks(); }, [user, loadNotebooks]);

  // Group notebooks by workspace
  const grouped = useMemo(() => {
    const groups: Record<string, { name: string; notebooks: NotebookWithWorkspace[] }> = {};
    for (const nb of notebooks) {
      const key = nb.workspace_id || "personal";
      if (!groups[key]) groups[key] = { name: nb.workspace_name || "Personal", notebooks: [] };
      groups[key].notebooks.push(nb);
    }
    return groups;
  }, [notebooks]);

  // Load page tree when notebook is selected
  const loadTree = useCallback(async (nb: NotebookWithWorkspace) => {
    try {
      const t = nb.workspace_id
        ? await listPageTree(nb.workspace_id, nb.id)
        : await listPersonalPageTree(nb.id);
      setTree(t);
    } catch { /* ignore */ }
  }, []);

  const handleSelectNotebook = useCallback((nb: NotebookWithWorkspace) => {
    setSelectedNotebook(nb);
    setSelectedPageId(null);
    setSelectedPage(null);
    loadTree(nb);
  }, [loadTree]);

  const handleSelectPage = useCallback(async (pageId: string) => {
    if (!selectedNotebook) return;
    setSelectedPageId(pageId);
    try {
      const p = selectedNotebook.workspace_id
        ? await getPage(selectedNotebook.workspace_id, selectedNotebook.id, pageId)
        : await getPersonalPage(selectedNotebook.id, pageId);
      setSelectedPage(p);
    } catch { setError("Failed to load page"); }
  }, [selectedNotebook]);

  const handleCreateNotebook = async () => {
    const name = prompt("Notebook name:");
    if (!name) return;
    try {
      const nb = await createPersonalNotebook(name);
      await loadNotebooks();
      handleSelectNotebook({ ...nb, workspace_name: null } as NotebookWithWorkspace);
    } catch (err) { setError(err instanceof Error ? err.message : "Failed to create notebook"); }
  };

  const handleCreatePage = useCallback(async (folderId: string | null) => {
    if (!selectedNotebook) return;
    const name = prompt("File name:");
    if (!name) return;
    try {
      const p = selectedNotebook.workspace_id
        ? await createPage(selectedNotebook.workspace_id, selectedNotebook.id, name, folderId || undefined)
        : await createPersonalPage(selectedNotebook.id, name, folderId || undefined);
      await loadTree(selectedNotebook);
      setSelectedPageId(p.id);
      setSelectedPage(p);
    } catch (err) { setError(err instanceof Error ? err.message : "Failed to create file"); }
  }, [selectedNotebook, loadTree]);

  const handleCreateFolder = useCallback(async () => {
    if (!selectedNotebook) return;
    const name = prompt("Folder name:");
    if (!name) return;
    try {
      selectedNotebook.workspace_id
        ? await createPageFolder(selectedNotebook.workspace_id, selectedNotebook.id, name)
        : await createPersonalPageFolder(selectedNotebook.id, name);
      await loadTree(selectedNotebook);
    } catch (err) { setError(err instanceof Error ? err.message : "Failed to create folder"); }
  }, [selectedNotebook, loadTree]);

  const handleDeletePage = useCallback(async (pageId: string) => {
    if (!selectedNotebook || !confirm("Delete this file?")) return;
    try {
      selectedNotebook.workspace_id
        ? await deletePage(selectedNotebook.workspace_id, selectedNotebook.id, pageId)
        : await deletePersonalPage(selectedNotebook.id, pageId);
      if (selectedPageId === pageId) { setSelectedPageId(null); setSelectedPage(null); }
      await loadTree(selectedNotebook);
    } catch (err) { setError(err instanceof Error ? err.message : "Failed to delete"); }
  }, [selectedNotebook, selectedPageId, loadTree]);

  const handleDeleteFolder = useCallback(async (folderId: string) => {
    if (!selectedNotebook || !confirm("Delete this folder?")) return;
    try {
      selectedNotebook.workspace_id
        ? await deletePageFolder(selectedNotebook.workspace_id, selectedNotebook.id, folderId)
        : await deletePersonalPageFolder(selectedNotebook.id, folderId);
      setSelectedPageId(null); setSelectedPage(null);
      await loadTree(selectedNotebook);
    } catch (err) { setError(err instanceof Error ? err.message : "Failed to delete folder"); }
  }, [selectedNotebook, loadTree]);

  const handleRenamePage = useCallback(async (pageId: string, currentName: string) => {
    if (!selectedNotebook) return;
    const name = prompt("New name:", currentName);
    if (!name || name === currentName) return;
    try {
      const updated = selectedNotebook.workspace_id
        ? await updatePage(selectedNotebook.workspace_id, selectedNotebook.id, pageId, { name })
        : await updatePersonalPage(selectedNotebook.id, pageId, { name });
      if (selectedPageId === pageId) setSelectedPage(updated);
      await loadTree(selectedNotebook);
    } catch (err) { setError(err instanceof Error ? err.message : "Failed to rename"); }
  }, [selectedNotebook, selectedPageId, loadTree]);

  const handleRenameFolder = useCallback(async (folderId: string, currentName: string) => {
    if (!selectedNotebook) return;
    const name = prompt("New name:", currentName);
    if (!name || name === currentName) return;
    try {
      selectedNotebook.workspace_id
        ? await renamePageFolder(selectedNotebook.workspace_id, selectedNotebook.id, folderId, name)
        : await renamePersonalPageFolder(selectedNotebook.id, folderId, name);
      await loadTree(selectedNotebook);
    } catch (err) { setError(err instanceof Error ? err.message : "Failed to rename folder"); }
  }, [selectedNotebook, loadTree]);

  const handleMovePage = useCallback(async (pageId: string, folderId: string | null) => {
    if (!selectedNotebook) return;
    try {
      const data = folderId ? { folder_id: folderId } : { move_to_root: true };
      const updated = selectedNotebook.workspace_id
        ? await updatePage(selectedNotebook.workspace_id, selectedNotebook.id, pageId, data)
        : await updatePersonalPage(selectedNotebook.id, pageId, data);
      if (selectedPageId === pageId) setSelectedPage(updated);
      await loadTree(selectedNotebook);
    } catch (err) { setError(err instanceof Error ? err.message : "Failed to move"); }
  }, [selectedNotebook, selectedPageId, loadTree]);

  const handleSavePage = useCallback(async (content: string) => {
    if (!selectedNotebook || !selectedPageId) return;
    try {
      selectedNotebook.workspace_id
        ? await updatePage(selectedNotebook.workspace_id, selectedNotebook.id, selectedPageId, { content })
        : await updatePersonalPage(selectedNotebook.id, selectedPageId, { content });
    } catch (err) { setError(err instanceof Error ? err.message : "Failed to save"); }
  }, [selectedNotebook, selectedPageId]);

  if (loading) return <div className="min-h-screen flex items-center justify-center text-muted">Loading...</div>;
  if (!user) { router.push("/login"); return null; }

  return (
    <AppShell user={user} onLogout={logout}>
      <div className="flex h-full overflow-hidden">
        {/* Notebook list */}
        <div className="w-[200px] flex-shrink-0 bg-surface border-r border-border overflow-y-auto">
          <div className="px-3 py-3 flex items-center justify-between border-b border-border">
            <span className="text-[10px] font-medium text-muted uppercase tracking-wider">Notebooks</span>
            <button onClick={handleCreateNotebook} className="text-xs text-brand hover:text-brand-hover">+ New</button>
          </div>
          {Object.entries(grouped).map(([key, group]) => (
            <div key={key} className="px-2 py-2">
              <div className="text-[10px] font-medium text-muted uppercase tracking-wider px-2 mb-1">{group.name}</div>
              {group.notebooks.map((nb) => (
                <div key={nb.id} className="group flex items-center">
                  <button
                    onClick={() => handleSelectNotebook(nb)}
                    className={`flex-1 text-left px-2 py-1.5 rounded text-sm truncate transition-colors ${
                      selectedNotebook?.id === nb.id ? "bg-brand/10 text-brand font-medium" : "text-dim hover:text-foreground hover:bg-raised"
                    }`}
                  >
                    {nb.name}
                  </button>
                  {!nb.workspace_id && (
                    <button
                      onClick={async (e) => {
                        e.stopPropagation();
                        if (!confirm(`Delete notebook "${nb.name}"?`)) return;
                        try {
                          await deletePersonalNotebook(nb.id);
                          if (selectedNotebook?.id === nb.id) { setSelectedNotebook(null); setTree({ folders: [], root_files: [] }); setSelectedPage(null); }
                          loadNotebooks();
                        } catch { /* ignore */ }
                      }}
                      className="text-red-400 hover:text-red-300 text-xs px-1 opacity-0 group-hover:opacity-100 transition-opacity flex-shrink-0"
                      title="Delete notebook"
                    >
                      &times;
                    </button>
                  )}
                </div>
              ))}
            </div>
          ))}
          {notebooks.length === 0 && <div className="px-4 py-8 text-center text-muted text-sm">No notebooks yet</div>}
        </div>

        {/* File tree (when notebook selected) */}
        {selectedNotebook && (
          <div className="w-[200px] flex-shrink-0 bg-surface border-r border-border overflow-hidden">
            <NotebookTreeComponent
              tree={tree}
              selectedFileId={selectedPageId}
              onSelectFile={handleSelectPage}
              onCreateFile={handleCreatePage}
              onCreateFolder={handleCreateFolder}
              onDeleteFile={handleDeletePage}
              onDeleteFolder={handleDeleteFolder}
              onRenameFile={handleRenamePage}
              onRenameFolder={handleRenameFolder}
              onMoveFile={handleMovePage}
            />
          </div>
        )}

        {/* Editor */}
        <div className="flex-1 flex flex-col overflow-hidden">
          {error && (
            <div className="bg-red-900/30 border-b border-red-800 text-red-400 text-sm px-4 py-2">
              {error}<button onClick={() => setError("")} className="ml-2 text-red-500 hover:text-red-300">&times;</button>
            </div>
          )}
          {selectedPage ? (
            <MarkdownEditor
              key={selectedPage.id}
              notebookId={selectedNotebook?.id || null}
              workspaceId={selectedNotebook?.workspace_id || null}
              file={selectedPage}
              onSave={handleSavePage}
            />
          ) : (
            <div className="flex-1 flex items-center justify-center text-muted">
              <div className="text-center">
                {selectedNotebook
                  ? <><p className="text-lg mb-2">Select a file to edit</p><p className="text-sm">or create one from the sidebar</p></>
                  : <><p className="text-lg mb-2">Select a notebook</p><p className="text-sm">or create a new one</p></>
                }
              </div>
            </div>
          )}
        </div>
      </div>
    </AppShell>
  );
}
