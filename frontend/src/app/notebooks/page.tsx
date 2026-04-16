"use client";

import { Suspense, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import Link from "next/link";
import AppShell from "../../components/AppShell";
import NotebookTreeComponent from "../../components/workspace/FileTree";
import MarkdownEditor, { SaveStatus } from "../../components/workspace/MarkdownEditor";
import { useAuth } from "../../hooks/useAuth";
import {
  listAllNotebooks,
  listNotebooks,
  createNotebook,
  deleteNotebook,
  listPageTree,
  createPage,
  getPage,
  updatePage,
  deletePage,
  createPageFolder,
  renamePageFolder,
  deletePageFolder,
  getBacklinks,
  semanticSearchPages,
  listAllTables,
  listTables,
  createTable,
  deleteTable,
} from "../../lib/api";
import { Notebook, NotebookPage, NotebookWithWorkspace, PageLink, PageTree, TableWithWorkspace } from "../../lib/types";

type WikiTab = "pages" | "tables";

export default function WikiPage() {
  return (
    <Suspense fallback={<div className="min-h-screen flex items-center justify-center text-muted">Loading...</div>}>
      <WikiPageInner />
    </Suspense>
  );
}

function WikiPageInner() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const wsId = searchParams.get("ws");
  const tabParam = searchParams.get("tab");
  const nbParam = searchParams.get("nb");
  const pageParam = searchParams.get("page");
  const { user, loading, logout } = useAuth();

  // Tab state — sync with URL
  const [activeTab, setActiveTab] = useState<WikiTab>((tabParam as WikiTab) || "pages");
  useEffect(() => {
    if (tabParam === "tables" || tabParam === "pages") {
      setActiveTab(tabParam);
    }
  }, [tabParam]);

  // --- Pages tab state ---
  const [notebooks, setNotebooks] = useState<NotebookWithWorkspace[]>([]);
  const [selectedNotebook, setSelectedNotebook] = useState<NotebookWithWorkspace | null>(null);
  const [tree, setTree] = useState<PageTree>({ folders: [], root_files: [] });
  const [selectedPageId, setSelectedPageId] = useState<string | null>(null);
  const [selectedPage, setSelectedPage] = useState<NotebookPage | null>(null);
  const [backlinks, setBacklinks] = useState<PageLink[]>([]);


  const [saveStatus, setSaveStatus] = useState<SaveStatus>("saved");
  const [semanticQuery, setSemanticQuery] = useState("");
  const [semanticResults, setSemanticResults] = useState<NotebookPage[]>([]);
  const [semanticSearching, setSemanticSearching] = useState(false);
  const [error, setError] = useState("");

  // --- Tables tab state ---
  const [tables, setTables] = useState<TableWithWorkspace[]>([]);
  const [tablesError, setTablesError] = useState("");

  // --- Notebooks loading ---
  const loadNotebooks = useCallback(async () => {
    try {
      if (wsId) {
        const res = await listNotebooks(wsId);
        const nbs = (res?.notebooks ?? []).map((n: any) => ({ ...n, workspace_id: wsId, workspace_name: "" }));
        setNotebooks(nbs);
      } else {
        const res = await listAllNotebooks();
        setNotebooks(res?.notebooks ?? []);
      }
    } catch { /* ignore */ }
  }, [wsId]);

  // --- Tables loading ---
  const loadTables = useCallback(async () => {
    try {
      if (wsId) {
        const res = await listTables(wsId);
        const tbls = (res?.tables ?? []).map((t: any) => ({ ...t, workspace_id: wsId, workspace_name: "" }));
        setTables(tbls);
      } else {
        const res = await listAllTables();
        setTables(res?.tables ?? []);
      }
    } catch { /* ignore */ }
  }, [wsId]);

  useEffect(() => {
    if (user) {
      loadNotebooks();
      loadTables();
    }
  }, [user, loadNotebooks, loadTables]);

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

  // Group tables by workspace
  const groupedTables = useMemo(() => {
    const groups: Record<string, { name: string; tables: TableWithWorkspace[] }> = {};
    for (const t of tables) {
      const key = t.workspace_id || "personal";
      if (!groups[key]) groups[key] = { name: t.workspace_name || "Personal", tables: [] };
      groups[key].tables.push(t);
    }
    return groups;
  }, [tables]);

  // Load page tree when notebook is selected
  const loadTree = useCallback(async (nb: NotebookWithWorkspace) => {
    try {
      const t = await listPageTree(nb.workspace_id, nb.id);
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
      const p = await getPage(selectedNotebook.workspace_id, selectedNotebook.id, pageId);
      setSelectedPage(p);
      // Load backlinks
      try {
        const bl = await getBacklinks(selectedNotebook.workspace_id, selectedNotebook.id, pageId);
        setBacklinks(bl);
      } catch { /* backlinks are optional */ }
    } catch { setError("Failed to load page"); }
  }, [selectedNotebook]);

  // Deep-link: auto-select notebook and page from URL params (once on load)
  const deepLinked = useRef(false);
  useEffect(() => {
    if (deepLinked.current || !nbParam || notebooks.length === 0) return;
    const nb = notebooks.find((n) => n.id === nbParam);
    if (!nb) return;
    deepLinked.current = true;
    handleSelectNotebook(nb);
    // Clear URL params so they don't interfere with future navigation
    const url = new URL(window.location.href);
    url.searchParams.delete("nb");
    url.searchParams.delete("page");
    window.history.replaceState({}, "", url.toString());
  }, [nbParam, notebooks, handleSelectNotebook]);

  useEffect(() => {
    if (!pageParam || !deepLinked.current) return;
    if (!selectedNotebook || selectedPageId !== null) return;
    handleSelectPage(pageParam);
  }, [pageParam, selectedNotebook, selectedPageId, handleSelectPage]);

  // Navigate to a page by name (for wiki link clicks)
  const handleNavigateToPage = useCallback((pageName: string) => {
    // Find page in tree by name
    for (const f of tree.root_files) {
      if (f.name === pageName) {
        handleSelectPage(f.id);
        return;
      }
    }
    for (const folder of tree.folders) {
      for (const f of folder.files) {
        if (f.name === pageName) {
          handleSelectPage(f.id);
          return;
        }
      }
    }
  }, [tree, handleSelectPage]);

  // Compute breadcrumb path for current page
  const breadcrumbs = useMemo(() => {
    const parts: { label: string; onClick?: () => void }[] = [];
    if (selectedNotebook) {
      const wsName = selectedNotebook.workspace_name || "Personal";
      parts.push({ label: wsName });
      parts.push({
        label: selectedNotebook.name,
        onClick: () => { setSelectedPageId(null); setSelectedPage(null); },
      });
      if (selectedPage) {
        // Find which folder this page is in
        for (const folder of tree.folders) {
          for (const f of folder.files) {
            if (f.id === selectedPage.id) {
              parts.push({ label: folder.name });
              break;
            }
          }
        }
        parts.push({ label: selectedPage.name });
      }
    }
    return parts;
  }, [selectedNotebook, selectedPage, tree]);




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
      const nb = await createNotebook(null, name);
      await loadNotebooks();
      handleSelectNotebook({ ...nb, workspace_name: null } as NotebookWithWorkspace);
    } catch (err) { setError(err instanceof Error ? err.message : "Failed to create notebook"); }
  };

  const handleCreatePage = useCallback(async (folderId: string | null) => {
    if (!selectedNotebook) return;
    const name = prompt("Page name:");
    if (!name) return;
    try {
      const p = await createPage(selectedNotebook.workspace_id, selectedNotebook.id, name, folderId || undefined);
      await loadTree(selectedNotebook);
      setSelectedPageId(p.id);
      setSelectedPage(p);
    } catch (err) { setError(err instanceof Error ? err.message : "Failed to create page"); }
  }, [selectedNotebook, loadTree]);

  const handleCreateFolder = useCallback(async () => {
    if (!selectedNotebook) return;
    const name = prompt("Folder name:");
    if (!name) return;
    try {
      await createPageFolder(selectedNotebook.workspace_id, selectedNotebook.id, name);
      await loadTree(selectedNotebook);
    } catch (err) { setError(err instanceof Error ? err.message : "Failed to create folder"); }
  }, [selectedNotebook, loadTree]);

  const handleDeletePage = useCallback(async (pageId: string) => {
    if (!selectedNotebook || !confirm("Delete this page?")) return;
    try {
      await deletePage(selectedNotebook.workspace_id, selectedNotebook.id, pageId);
      if (selectedPageId === pageId) { setSelectedPageId(null); setSelectedPage(null); }
      await loadTree(selectedNotebook);
    } catch (err) { setError(err instanceof Error ? err.message : "Failed to delete"); }
  }, [selectedNotebook, selectedPageId, loadTree]);

  const handleDeleteFolder = useCallback(async (folderId: string) => {
    if (!selectedNotebook || !confirm("Delete this folder?")) return;
    try {
      await deletePageFolder(selectedNotebook.workspace_id, selectedNotebook.id, folderId);
      setSelectedPageId(null); setSelectedPage(null);
      await loadTree(selectedNotebook);
    } catch (err) { setError(err instanceof Error ? err.message : "Failed to delete folder"); }
  }, [selectedNotebook, loadTree]);

  const handleRenamePage = useCallback(async (pageId: string, currentName: string) => {
    if (!selectedNotebook) return;
    const name = prompt("New name:", currentName);
    if (!name || name === currentName) return;
    try {
      const updated = await updatePage(selectedNotebook.workspace_id, selectedNotebook.id, pageId, { name });
      if (selectedPageId === pageId) setSelectedPage(updated);
      await loadTree(selectedNotebook);
    } catch (err) { setError(err instanceof Error ? err.message : "Failed to rename"); }
  }, [selectedNotebook, selectedPageId, loadTree]);

  const handleInlineRename = useCallback(async (name: string) => {
    if (!selectedNotebook || !selectedPageId) return;
    try {
      const updated = await updatePage(selectedNotebook.workspace_id, selectedNotebook.id, selectedPageId, { name });
      setSelectedPage(updated);
      await loadTree(selectedNotebook);
    } catch { /* silent — title updates are best-effort */ }
  }, [selectedNotebook, selectedPageId, loadTree]);

  const handleRenameFolder = useCallback(async (folderId: string, currentName: string) => {
    if (!selectedNotebook) return;
    const name = prompt("New name:", currentName);
    if (!name || name === currentName) return;
    try {
      await renamePageFolder(selectedNotebook.workspace_id, selectedNotebook.id, folderId, name);
      await loadTree(selectedNotebook);
    } catch (err) { setError(err instanceof Error ? err.message : "Failed to rename folder"); }
  }, [selectedNotebook, loadTree]);

  const handleMovePage = useCallback(async (pageId: string, folderId: string | null) => {
    if (!selectedNotebook) return;
    try {
      const data = folderId ? { folder_id: folderId } : { move_to_root: true };
      const updated = await updatePage(selectedNotebook.workspace_id, selectedNotebook.id, pageId, data);
      if (selectedPageId === pageId) setSelectedPage(updated);
      await loadTree(selectedNotebook);
    } catch (err) { setError(err instanceof Error ? err.message : "Failed to move"); }
  }, [selectedNotebook, selectedPageId, loadTree]);

  const handleSavePage = useCallback(async (content: string) => {
    if (!selectedNotebook || !selectedPageId) return;
    try {
      await updatePage(selectedNotebook.workspace_id, selectedNotebook.id, selectedPageId, { content });
    } catch (err) { setError(err instanceof Error ? err.message : "Failed to save"); }
  }, [selectedNotebook, selectedPageId]);

  const handleCreateTable = async () => {
    const name = prompt("Table name:");
    if (!name) return;
    try {
      const table = await createTable(null, name);
      router.push(`/tables/${table.id}`);
    } catch (err) { setTablesError(err instanceof Error ? err.message : "Failed to create table"); }
  };

  useEffect(() => { if (!loading && !user) router.push("/login"); }, [user, loading, router]);
  if (loading) return <div className="min-h-screen flex items-center justify-center text-muted">Loading...</div>;
  if (!user) return null;

  return (
    <AppShell user={user} onLogout={logout}>
      <div className="flex flex-col h-full overflow-hidden">
        {/* Tab bar */}
        <div className="flex items-center gap-0 px-4 border-b border-border bg-surface flex-shrink-0">
          <button
            onClick={() => setActiveTab("pages")}
            className={`px-4 py-2.5 text-sm font-medium transition-colors relative ${
              activeTab === "pages"
                ? "text-brand"
                : "text-dim hover:text-foreground"
            }`}
          >
            Pages
            {activeTab === "pages" && (
              <span className="absolute bottom-0 left-0 right-0 h-[2px] bg-brand rounded-t" />
            )}
          </button>
          <button
            onClick={() => setActiveTab("tables")}
            className={`px-4 py-2.5 text-sm font-medium transition-colors relative ${
              activeTab === "tables"
                ? "text-brand"
                : "text-dim hover:text-foreground"
            }`}
          >
            Tables
            {activeTab === "tables" && (
              <span className="absolute bottom-0 left-0 right-0 h-[2px] bg-brand rounded-t" />
            )}
          </button>
        </div>

        {/* Pages tab */}
        {activeTab === "pages" && !selectedNotebook && (
          /* ── Notebook list (landing) ── */
          <div className="flex-1 overflow-y-auto">
            <div className="max-w-3xl mx-auto w-full px-4 py-8">
              <div className="flex items-center justify-between mb-6">
                <h2 className="text-xl font-bold text-foreground font-display">Notebooks</h2>
                <button onClick={handleCreateNotebook} className="text-sm bg-brand hover:bg-brand-hover text-foreground px-3 py-1.5 rounded transition-colors">
                  New Notebook
                </button>
              </div>
              {error && <p className="text-red-400 text-sm mb-4">{error}<button onClick={() => setError("")} className="ml-2 text-red-500">&times;</button></p>}
              {notebooks.length === 0 ? (
                <p className="text-muted text-sm">No notebooks yet. Create one to start writing wiki pages.</p>
              ) : (
                <div className="space-y-2">
                  {Object.entries(grouped).map(([key, group]) => (
                    <div key={key}>
                      <p className="text-[10px] font-medium text-muted uppercase tracking-wider mb-2">{group.name}</p>
                      {group.notebooks.map((nb) => (
                        <button
                          key={nb.id}
                          onClick={() => handleSelectNotebook(nb)}
                          className="w-full text-left flex items-center gap-3 px-4 py-3 rounded-lg border border-border bg-surface hover:bg-raised transition-colors mb-2"
                        >
                          <div className="w-8 h-8 rounded-md bg-green-500/15 text-green-500 flex items-center justify-center text-xs font-bold flex-shrink-0">N</div>
                          <div className="min-w-0 flex-1">
                            <div className="text-sm font-medium text-foreground">{nb.name}</div>
                            {nb.description && <div className="text-xs text-muted truncate">{nb.description}</div>}
                          </div>
                        </button>
                      ))}
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>
        )}

        {activeTab === "pages" && selectedNotebook && (
          /* ── Notebook open: sidebar + editor ── */
          <div className="flex flex-1 overflow-hidden">
            {/* Sidebar: file tree */}
            <div className="w-[240px] flex-shrink-0 bg-surface border-r border-border overflow-hidden flex flex-col">

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

              {/* File tree */}
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

            {/* Editor + Wiki Panel */}
            <div className="flex-1 flex flex-col overflow-hidden">
              {error && (
                <div className="bg-red-900/30 border-b border-red-800 text-red-400 text-sm px-4 py-2">
                  {error}<button onClick={() => setError("")} className="ml-2 text-red-500 hover:text-red-300">&times;</button>
                </div>
              )}

              {/* Breadcrumbs */}
              <div className="flex items-center justify-between px-4 py-1.5 border-b border-border bg-surface">
                <nav className="flex items-center gap-1 text-[12px] text-muted min-w-0">
                  <button
                    onClick={() => { setSelectedNotebook(null); setSelectedPage(null); setSelectedPageId(null); setTree({ folders: [], root_files: [] }); }}
                    className="hover:text-foreground transition-colors"
                  >
                    Wiki
                  </button>
                  <span className="text-border">/</span>
                  <button
                    onClick={() => { setSelectedPage(null); setSelectedPageId(null); }}
                    className="hover:text-foreground transition-colors truncate"
                  >
                    {selectedNotebook.name}
                  </button>
                  {selectedPage && (
                    <>
                      <span className="text-border">/</span>
                      <span className="text-foreground font-medium truncate">{selectedPage.name}</span>
                    </>
                  )}
                </nav>
                {selectedPage && (
                  <span
                    className={`w-2 h-2 rounded-full flex-shrink-0 ${
                      saveStatus === "saved" ? "bg-green-400" : "bg-yellow-400"
                    }`}
                    title={saveStatus === "saving" ? "Saving..." : saveStatus === "dirty" ? "Unsaved changes" : "Saved"}
                  />
                )}
              </div>

              {selectedPage ? (
                <div className="flex-1 flex flex-col overflow-hidden">
                  <div className="flex-1 overflow-y-auto">
                    <MarkdownEditor
                      key={selectedPage.id}
                      notebookId={selectedNotebook.id}
                      workspaceId={selectedNotebook.workspace_id || null}
                      file={selectedPage}
                      onSave={handleSavePage}
                      onSaveStatusChange={setSaveStatus}
                      onRename={handleInlineRename}
                      pageNames={pageNames}
                      onNavigateToPage={handleNavigateToPage}
                    />

                    {/* Backlinks */}
                    {backlinks.length > 0 && (
                      <div className="max-w-[720px] mx-auto w-full px-8 pb-10">
                        <div className="border-t border-border/50 pt-6 mt-2">
                          <h4 className="text-[11px] font-medium text-muted uppercase tracking-wider mb-3">
                            Linked from
                          </h4>
                          <div className="flex flex-wrap gap-x-4 gap-y-1">
                            {backlinks.map((bl) => (
                              <button
                                key={bl.id}
                                onClick={() => handleSelectPage(bl.id)}
                                className="text-sm text-muted hover:text-brand transition-colors"
                              >
                                {bl.name}
                              </button>
                            ))}
                          </div>
                        </div>
                      </div>
                    )}
                  </div>
                </div>
              ) : (
                <div className="flex-1 flex items-center justify-center text-muted">
                  <p className="text-sm">Select a page or create one from the sidebar</p>
                </div>
              )}
            </div>
          </div>
        )}

        {/* Tables tab */}
        {activeTab === "tables" && (
          <div className="flex-1 overflow-y-auto">
            <div className="max-w-3xl mx-auto w-full px-4 py-8">
              <div className="flex items-center justify-between mb-6">
                <h2 className="text-xl font-bold text-foreground font-display">Tables</h2>
                <button onClick={handleCreateTable} className="text-sm bg-brand hover:bg-brand-hover text-foreground px-3 py-1.5 rounded transition-colors">
                  New Table
                </button>
              </div>
              {tablesError && <p className="text-red-400 text-sm mb-4">{tablesError}</p>}
              {tables.length === 0 ? (
                <p className="text-muted text-sm">No tables yet. Create one to get started -- structured data that agents and humans can read and write.</p>
              ) : (
                Object.entries(groupedTables).map(([key, group]) => (
                  <section key={key} className="mb-6">
                    <h3 className="text-sm font-medium text-muted uppercase tracking-wider mb-2">{group.name}</h3>
                    <div className="space-y-1">
                      {group.tables.map((table) => (
                        <Link
                          key={table.id}
                          href={`/tables/${table.id}${table.workspace_id ? `?workspaceId=${table.workspace_id}` : ""}`}
                          className="group flex items-center gap-3 px-3 py-2.5 rounded-lg hover:bg-raised transition-colors"
                        >
                          <div className="w-7 h-7 rounded-md bg-cyan-500/15 text-cyan-500 flex items-center justify-center text-xs font-bold flex-shrink-0">
                            T
                          </div>
                          <div className="min-w-0 flex-1">
                            <div className="text-sm text-foreground truncate">{table.name}</div>
                            {table.description && <div className="text-xs text-muted truncate">{table.description}</div>}
                          </div>
                          <span className="text-[10px] text-muted bg-raised px-1.5 py-0.5 rounded font-mono flex-shrink-0">
                            {table.columns.length} cols
                          </span>
                          <span className="text-[10px] text-muted bg-raised px-1.5 py-0.5 rounded font-mono flex-shrink-0">
                            {table.row_count ?? 0} rows
                          </span>
                          <span className="text-xs text-muted flex-shrink-0">
                            {new Date(table.updated_at).toLocaleDateString()}
                          </span>
                          {!table.workspace_id && (
                            <button
                              onClick={async (e) => {
                                e.preventDefault();
                                e.stopPropagation();
                                if (!confirm("Delete this table?")) return;
                                try {
                                  await deleteTable(null, table.id);
                                  loadTables();
                                } catch (err) { setTablesError(err instanceof Error ? err.message : "Failed to delete"); }
                              }}
                              className="text-xs text-red-400 hover:text-red-300 px-2 py-1 opacity-0 group-hover:opacity-100 transition-opacity flex-shrink-0"
                            >
                              Delete
                            </button>
                          )}
                        </Link>
                      ))}
                    </div>
                  </section>
                ))
              )}
            </div>
          </div>
        )}
      </div>
    </AppShell>
  );
}
