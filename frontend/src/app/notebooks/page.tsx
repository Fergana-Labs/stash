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
  getBacklinks,
  getPersonalBacklinks,
  getPageGraph,
  getPersonalPageGraph,
  autoIndexNotebook,
  semanticSearchPages,
} from "../../lib/api";
import PageGraphView from "../../components/workspace/PageGraphView";
import { Notebook, NotebookPage, NotebookWithWorkspace, PageGraph, PageLink, PageTree } from "../../lib/types";

export default function NotebooksPage() {
  const router = useRouter();
  const { user, loading, logout } = useAuth();
  const [notebooks, setNotebooks] = useState<NotebookWithWorkspace[]>([]);
  const [selectedNotebook, setSelectedNotebook] = useState<NotebookWithWorkspace | null>(null);
  const [tree, setTree] = useState<PageTree>({ folders: [], root_files: [] });
  const [selectedPageId, setSelectedPageId] = useState<string | null>(null);
  const [selectedPage, setSelectedPage] = useState<NotebookPage | null>(null);
  const [backlinks, setBacklinks] = useState<PageLink[]>([]);
  const [showGraph, setShowGraph] = useState(false);
  const [pageGraph, setPageGraph] = useState<PageGraph | null>(null);
  const [semanticQuery, setSemanticQuery] = useState("");
  const [semanticResults, setSemanticResults] = useState<NotebookPage[]>([]);
  const [semanticSearching, setSemanticSearching] = useState(false);
  const [error, setError] = useState("");

  const loadNotebooks = useCallback(async () => {
    try {
      const res = await listAllNotebooks();
      setNotebooks(res?.notebooks ?? []);
    } catch { /* ignore */ }
  }, []);

  useEffect(() => { if (user) loadNotebooks(); }, [user, loadNotebooks]);

  // Extract page names from tree for wiki link autocomplete
  const pageNames = useMemo(() => {
    const names: string[] = [];
    for (const f of tree.root_files) names.push(f.name);
    for (const folder of tree.folders) {
      for (const f of folder.files) names.push(f.name);
    }
    return names;
  }, [tree]);

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
    setBacklinks([]);
    try {
      const p = selectedNotebook.workspace_id
        ? await getPage(selectedNotebook.workspace_id, selectedNotebook.id, pageId)
        : await getPersonalPage(selectedNotebook.id, pageId);
      setSelectedPage(p);
      // Load backlinks
      try {
        const bl = selectedNotebook.workspace_id
          ? await getBacklinks(selectedNotebook.workspace_id, selectedNotebook.id, pageId)
          : await getPersonalBacklinks(selectedNotebook.id, pageId);
        setBacklinks(bl);
      } catch { /* backlinks are optional */ }
    } catch { setError("Failed to load page"); }
  }, [selectedNotebook]);

  const handleShowGraph = useCallback(async () => {
    if (!selectedNotebook) return;
    try {
      const g = selectedNotebook.workspace_id
        ? await getPageGraph(selectedNotebook.workspace_id, selectedNotebook.id)
        : await getPersonalPageGraph(selectedNotebook.id);
      setPageGraph(g);
      setShowGraph(true);
    } catch { setError("Failed to load page graph"); }
  }, [selectedNotebook]);

  const handleAutoIndex = useCallback(async () => {
    if (!selectedNotebook?.workspace_id) return;
    try {
      await autoIndexNotebook(selectedNotebook.workspace_id, selectedNotebook.id);
      loadTree(selectedNotebook);
    } catch { setError("Failed to generate index"); }
  }, [selectedNotebook, loadTree]);

  const handleSemanticSearch = useCallback(async () => {
    if (!selectedNotebook?.workspace_id || !semanticQuery.trim()) return;
    setSemanticSearching(true);
    try {
      const pages = await semanticSearchPages(
        selectedNotebook.workspace_id, selectedNotebook.id, semanticQuery.trim(),
      );
      setSemanticResults(pages);
    } catch { setSemanticResults([]); }
    setSemanticSearching(false);
  }, [selectedNotebook, semanticQuery]);

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
          <div className="w-[200px] flex-shrink-0 bg-surface border-r border-border overflow-hidden flex flex-col">
            {/* Semantic search */}
            {selectedNotebook.workspace_id && (
              <div className="px-2 pt-2 pb-1 border-b border-border">
                <div className="flex gap-1">
                  <input
                    type="text"
                    placeholder="Search pages..."
                    value={semanticQuery}
                    onChange={(e) => { setSemanticQuery(e.target.value); if (!e.target.value) setSemanticResults([]); }}
                    onKeyDown={(e) => e.key === "Enter" && handleSemanticSearch()}
                    className="flex-1 text-[11px] bg-raised border border-border rounded px-2 py-1 text-foreground placeholder:text-muted min-w-0"
                  />
                </div>
                {semanticSearching && <div className="text-[10px] text-muted px-1 py-1">Searching...</div>}
                {semanticResults.length > 0 && (
                  <div className="mt-1 space-y-0.5 max-h-[150px] overflow-y-auto">
                    {semanticResults.map((p) => (
                      <button
                        key={p.id}
                        onClick={() => { handleSelectPage(p.id); setSemanticResults([]); setSemanticQuery(""); }}
                        className="w-full text-left text-[11px] text-foreground hover:bg-raised px-2 py-1 rounded truncate"
                      >
                        {p.name}
                        {"similarity" in p && (
                          <span className="text-muted ml-1">
                            {Math.round(((p as unknown as Record<string, number>).similarity ?? 0) * 100)}%
                          </span>
                        )}
                      </button>
                    ))}
                  </div>
                )}
              </div>
            )}
            <div className="flex-1 overflow-hidden">
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
          </div>
        )}

        {/* Editor + Wiki Panel */}
        <div className="flex-1 flex flex-col overflow-hidden">
          {error && (
            <div className="bg-red-900/30 border-b border-red-800 text-red-400 text-sm px-4 py-2">
              {error}<button onClick={() => setError("")} className="ml-2 text-red-500 hover:text-red-300">&times;</button>
            </div>
          )}

          {/* Wiki toolbar */}
          {selectedNotebook && (
            <div className="flex items-center gap-2 px-4 py-1.5 border-b border-border bg-surface">
              <button
                onClick={handleShowGraph}
                className="text-xs text-dim hover:text-foreground px-2 py-1 rounded hover:bg-raised transition-colors"
              >
                Page Graph
              </button>
              {selectedNotebook.workspace_id && (
                <button
                  onClick={handleAutoIndex}
                  className="text-xs text-dim hover:text-foreground px-2 py-1 rounded hover:bg-raised transition-colors"
                >
                  Auto Index
                </button>
              )}
            </div>
          )}

          {/* Graph modal */}
          {showGraph && pageGraph && (
            <PageGraphView
              graph={pageGraph}
              onClose={() => setShowGraph(false)}
              onSelectPage={handleSelectPage}
            />
          )}

          {selectedPage ? (
            <div className="flex-1 flex flex-col overflow-hidden">
              <div className="flex-1 overflow-hidden">
                <MarkdownEditor
                  key={selectedPage.id}
                  notebookId={selectedNotebook?.id || null}
                  workspaceId={selectedNotebook?.workspace_id || null}
                  file={selectedPage}
                  onSave={handleSavePage}
                  pageNames={pageNames}
                />
              </div>

              {/* Backlinks panel */}
              {backlinks.length > 0 && (
                <div className="border-t border-border bg-surface px-4 py-3 flex-shrink-0">
                  <h4 className="text-[10px] font-medium text-muted uppercase tracking-wider mb-2">
                    Backlinks ({backlinks.length})
                  </h4>
                  <div className="flex flex-wrap gap-1.5">
                    {backlinks.map((bl) => (
                      <button
                        key={bl.id}
                        onClick={() => handleSelectPage(bl.id)}
                        className="text-xs text-brand hover:text-brand-hover bg-brand/5 hover:bg-brand/10 px-2 py-1 rounded transition-colors"
                      >
                        {bl.name}
                      </button>
                    ))}
                  </div>
                </div>
              )}
            </div>
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
