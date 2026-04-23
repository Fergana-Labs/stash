"use client";

import { Suspense, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import Link from "next/link";
import AppShell from "../../components/AppShell";
import { useBreadcrumbs, type Crumb } from "../../components/BreadcrumbContext";
import NotebookTreeComponent from "../../components/workspace/FileTree";
import MarkdownEditor, { SaveStatus } from "../../components/workspace/MarkdownEditor";
import { useAuth } from "../../hooks/useAuth";
import {
  listAllNotebooks,
  listNotebooks,
  createNotebook,
  deleteNotebook,
  listPageTree,
  listWorkspacePages,
  createPage,
  getPage,
  updatePage,
  deletePage,
  createPageFolder,
  renamePageFolder,
  deletePageFolder,
  getBacklinks,
  semanticSearchPages,
  WorkspacePageEntry,
} from "../../lib/api";
import { Notebook, NotebookPage, NotebookWithWorkspace, PageLink, PageTree } from "../../lib/types";

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
  const nbParam = searchParams.get("nb");
  const pageParam = searchParams.get("page");
  const { user, loading, logout } = useAuth();

  // --- Pages tab state ---
  const [notebooks, setNotebooks] = useState<NotebookWithWorkspace[]>([]);
  const [selectedNotebook, setSelectedNotebook] = useState<NotebookWithWorkspace | null>(null);
  const [tree, setTree] = useState<PageTree>({ folders: [], root_files: [] });
  const [selectedPageId, setSelectedPageId] = useState<string | null>(null);
  const [selectedPage, setSelectedPage] = useState<NotebookPage | null>(null);
  const [backlinks, setBacklinks] = useState<PageLink[]>([]);
  // Flat cross-notebook page index. Drives wiki-link autocomplete + lets
  // clicks on [[Some Page]] resolve to pages in other notebooks, not just
  // the currently selected one.
  const [workspacePages, setWorkspacePages] = useState<WorkspacePageEntry[]>([]);


  const [saveStatus, setSaveStatus] = useState<SaveStatus>("saved");
  const [semanticQuery, setSemanticQuery] = useState("");
  const [semanticResults, setSemanticResults] = useState<NotebookPage[]>([]);
  const [semanticSearching, setSemanticSearching] = useState(false);
  const [error, setError] = useState("");
  const [deepLinked, setDeepLinked] = useState(false);
  const [deepLinkedPage, setDeepLinkedPage] = useState(false);
  // --- Notebooks loading ---
  const loadNotebooks = useCallback(async () => {
    try {
      if (wsId) {
        const res = await listNotebooks(wsId);
        const nbs = (res?.notebooks ?? []).map((n: Notebook) => ({ ...n, workspace_id: wsId, workspace_name: "" }));
        setNotebooks(nbs);
      } else {
        const res = await listAllNotebooks();
        setNotebooks(res?.notebooks ?? []);
      }
    } catch { /* ignore */ }
  }, [wsId]);

  useEffect(() => {
    if (user) loadNotebooks();
  }, [user, loadNotebooks]);

  // Workspace switch: drop any notebook/page selection from the previous
  // workspace so we don't render stale content under the new scope.
  const prevWsIdRef = useRef<string | null>(wsId);
  useEffect(() => {
    if (prevWsIdRef.current === wsId) return;
    prevWsIdRef.current = wsId;
    setSelectedNotebook(null);
    setSelectedPageId(null);
    setSelectedPage(null);
    setTree({ folders: [], root_files: [] });
    setBacklinks([]);
    setDeepLinked(false);
    setDeepLinkedPage(false);
  }, [wsId]);

  // Cross-notebook page index for wiki links. Refreshed when the workspace
  // changes or when a page is created/deleted below.
  const loadWorkspacePages = useCallback(async () => {
    try {
      const pages = await listWorkspacePages(wsId);
      setWorkspacePages(pages);
    } catch {
      /* ignore — autocomplete just falls back to local tree */
    }
  }, [wsId]);

  useEffect(() => {
    if (user) loadWorkspacePages();
  }, [user, loadWorkspacePages]);

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

  // Deep-link: auto-select notebook (and optionally page) from URL params.
  // Both latches fire exactly once per workspace — a ref-based latch stops
  // the effect from re-firing when the user backs out via the crumb (state
  // clears, pageParam still in URL, effect would otherwise re-select).
  useEffect(() => {
    if (deepLinked) return;
    if (!nbParam) {
      setDeepLinked(true);
      return;
    }
    if (notebooks.length === 0) return;
    const nb = notebooks.find((n) => n.id === nbParam);
    if (!nb) return;
    setDeepLinked(true);
    handleSelectNotebook(nb);
  }, [deepLinked, nbParam, notebooks, handleSelectNotebook]);

  useEffect(() => {
    if (deepLinkedPage) return;
    if (!pageParam) {
      setDeepLinkedPage(true);
      return;
    }
    if (!selectedNotebook) return;
    setDeepLinkedPage(true);
    handleSelectPage(pageParam);
  }, [deepLinkedPage, pageParam, selectedNotebook, handleSelectPage]);

  // Keep the URL in sync with the current notebook/page selection and
  // make browser back/forward walk the reading trail. Every time state
  // changes to something the URL doesn't already reflect we pushState a
  // new entry; identity-match bails so deep-link consume + popstate
  // round-trips don't create duplicate history entries or infinite loops.
  useEffect(() => {
    if (!deepLinked) return;

    const current = new URL(window.location.href);
    const currentNb = current.searchParams.get("nb");
    const currentPage = current.searchParams.get("page");
    const desiredNb = selectedNotebook?.id ?? null;
    const desiredPage = selectedPageId ?? null;

    if (currentNb === desiredNb && currentPage === desiredPage) return;

    const url = new URL(window.location.href);
    if (desiredNb) url.searchParams.set("nb", desiredNb);
    else url.searchParams.delete("nb");
    if (desiredPage) url.searchParams.set("page", desiredPage);
    else url.searchParams.delete("page");
    window.history.pushState({}, "", url.toString());
  }, [deepLinked, selectedNotebook, selectedPageId]);

  // Browser back / forward → re-read URL params and sync state. Next's
  // useSearchParams doesn't observe pushState/popstate, so we listen
  // directly. The sync effect above short-circuits when URL already
  // matches, so setting state from here doesn't recursively push.
  useEffect(() => {
    const onPop = () => {
      const p = new URL(window.location.href).searchParams;
      const nbId = p.get("nb");
      const pageId = p.get("page");

      // Notebook changed.
      if (nbId !== (selectedNotebook?.id ?? null)) {
        if (nbId) {
          const target = notebooks.find((n) => n.id === nbId);
          if (target) {
            setSelectedNotebook(target);
            setSelectedPageId(null);
            setSelectedPage(null);
            loadTree(target);
          }
        } else {
          setSelectedNotebook(null);
          setSelectedPageId(null);
          setSelectedPage(null);
          setTree({ folders: [], root_files: [] });
        }
      }

      // Page changed (within the same notebook, or after above switch).
      if (pageId !== (selectedPageId ?? null)) {
        if (pageId) {
          setSelectedPageId(pageId);
          // Use a microtask to let the notebook switch settle first.
          void (async () => {
            const nb = nbId
              ? notebooks.find((n) => n.id === nbId) ?? selectedNotebook
              : selectedNotebook;
            if (!nb) return;
            try {
              const pg = await getPage(nb.workspace_id, nb.id, pageId);
              setSelectedPage(pg);
            } catch {
              /* leave previous content */
            }
          })();
        } else {
          setSelectedPageId(null);
          setSelectedPage(null);
        }
      }
    };

    window.addEventListener("popstate", onPop);
    return () => window.removeEventListener("popstate", onPop);
  }, [notebooks, selectedNotebook, selectedPageId, loadTree]);

  // Navigate to a page by name (for wiki link clicks)
  // Resolve a wiki-link's raw text (e.g. "page", "folder/page",
  // Editor clicks on `/notebooks?ws=...&nb=...&page=...` links come
  // through here so we can SPA-select the target without a full reload.
  const handleNavigateInternal = useCallback(async (href: string) => {
    const url = new URL(href, window.location.origin);
    if (url.pathname !== "/notebooks") {
      router.push(`${url.pathname}${url.search}`);
      return;
    }
    const nbId = url.searchParams.get("nb");
    const pageId = url.searchParams.get("page");
    if (!nbId || !pageId) return;

    if (selectedNotebook && nbId === selectedNotebook.id) {
      handleSelectPage(pageId);
      return;
    }
    const target = notebooks.find((n) => n.id === nbId);
    if (!target) return;
    setSelectedNotebook(target);
    setSelectedPageId(pageId);
    setBacklinks([]);
    setSelectedPage(null);
    const [p, t] = await Promise.all([
      getPage(target.workspace_id, target.id, pageId),
      listPageTree(target.workspace_id, target.id),
    ]);
    setTree(t);
    setSelectedPage(p);
    const bl = await getBacklinks(target.workspace_id, target.id, pageId);
    setBacklinks(bl);
  }, [router, selectedNotebook, handleSelectPage, notebooks]);

  // Folder the current page lives in, for header breadcrumbs. null if the
  // page sits at the notebook root or nothing is selected.
  const currentFolderName = useMemo(() => {
    if (!selectedPage) return null;
    for (const folder of tree.folders) {
      if (folder.files.some((f) => f.id === selectedPage.id)) return folder.name;
    }
    return null;
  }, [selectedPage, tree]);




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
      await loadWorkspacePages();
      setSelectedPageId(p.id);
      setSelectedPage(p);
    } catch (err) { setError(err instanceof Error ? err.message : "Failed to create page"); }
  }, [selectedNotebook, loadTree, loadWorkspacePages]);

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
      await loadWorkspacePages();
    } catch (err) { setError(err instanceof Error ? err.message : "Failed to delete"); }
  }, [selectedNotebook, selectedPageId, loadTree, loadWorkspacePages]);

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

  useEffect(() => { if (!loading && !user) router.push("/login"); }, [user, loading, router]);

  // Register crumbs for the TopBar.
  const crumbs: Crumb[] = (() => {
    const base: Crumb[] = [{ label: "Wiki", href: "/notebooks" }];
    if (selectedNotebook) {
      base.push({
        label: selectedNotebook.name,
        onClick: () => {
          setSelectedPage(null);
          setSelectedPageId(null);
        },
      });
      if (selectedPage) {
        if (currentFolderName) {
          base.push({ label: currentFolderName });
        }
        base.push({ label: selectedPage.name });
      }
    }
    return base;
  })();
  const depKey = `${selectedNotebook?.id ?? ""}:${selectedNotebook?.name ?? ""}:${currentFolderName ?? ""}:${selectedPage?.id ?? ""}:${selectedPage?.name ?? ""}`;
  useBreadcrumbs(crumbs, depKey);

  if (loading) return <div className="min-h-screen flex items-center justify-center text-muted">Loading...</div>;
  if (!user) return null;

  return (
    <AppShell user={user} onLogout={logout}>
      <div className="flex flex-col h-full overflow-hidden">
        {!selectedNotebook && (
          /* ── Notebook list (landing) ── */
          <div className="flex-1 overflow-y-auto">
            <div className="mx-auto w-full max-w-[1120px] px-8 pb-16 pt-8">
              <div className="mb-8 flex items-end justify-between gap-4">
                <h1 className="font-display text-[32px] font-bold tracking-[-0.02em] text-foreground">
                  Wiki
                </h1>
                <button
                  onClick={handleCreateNotebook}
                  className="inline-flex h-9 items-center rounded-md bg-brand px-3.5 text-[13px] font-medium text-white shadow-sm transition hover:bg-brand-hover"
                >
                  + Page
                </button>
              </div>
              {error && (
                <p className="mb-4 text-[13px] text-red-500">
                  {error}
                  <button onClick={() => setError("")} className="ml-2 text-red-500">
                    &times;
                  </button>
                </p>
              )}
              {notebooks.length === 0 ? (
                <p className="text-[13px] text-muted">
                  No notebooks yet. Create one to start writing wiki pages.
                </p>
              ) : (
                <div className="flex flex-col gap-2">
                  {notebooks.map((nb) => (
                    <button
                      key={nb.id}
                      onClick={() => handleSelectNotebook(nb)}
                      className="flex w-full items-center gap-3 rounded-lg border border-border-subtle bg-base px-4 py-3.5 text-left transition-colors hover:border-brand"
                    >
                      <div className="flex h-8 w-8 flex-shrink-0 items-center justify-center rounded-md bg-raised font-mono text-[12px] font-bold text-muted">
                        W
                      </div>
                      <div className="min-w-0 flex-1">
                        <div className="text-[14px] font-semibold text-foreground">
                          {nb.name}
                        </div>
                        {nb.description && (
                          <div className="truncate text-[12px] text-dim">
                            {nb.description}
                          </div>
                        )}
                      </div>
                      <span className="font-mono text-[11px] text-muted">→</span>
                    </button>
                  ))}
                </div>
              )}
            </div>
          </div>
        )}

        {selectedNotebook && (
          /* ── Notebook open: sidebar + editor ── */
          <div className="flex flex-1 overflow-hidden">
            {/* Sidebar: file tree */}
            <div className="flex w-[260px] flex-shrink-0 flex-col overflow-hidden border-r border-border bg-surface">
              {selectedNotebook.workspace_id && (
                <div className="border-b border-border-subtle px-3 py-3">
                  <input
                    type="text"
                    placeholder="Search pages…"
                    value={semanticQuery}
                    onChange={(e) => {
                      setSemanticQuery(e.target.value);
                      if (!e.target.value) setSemanticResults([]);
                    }}
                    onKeyDown={(e) => e.key === "Enter" && handleSemanticSearch()}
                    className="w-full rounded-md border border-border bg-base px-2.5 py-1.5 text-[12px] text-foreground placeholder:text-muted focus:border-brand focus:outline-none focus:shadow-[0_0_0_3px_rgba(249,115,22,0.2)]"
                  />
                  {semanticSearching && (
                    <div className="mt-1 px-1 text-[10px] text-muted">Searching…</div>
                  )}
                  {semanticResults.length > 0 && (
                    <div className="mt-1.5 max-h-[160px] space-y-0.5 overflow-y-auto">
                      {semanticResults.map((p) => (
                        <button
                          key={p.id}
                          onClick={() => {
                            handleSelectPage(p.id);
                            setSemanticResults([]);
                            setSemanticQuery("");
                          }}
                          className="flex w-full items-center justify-between gap-2 truncate rounded px-2 py-1 text-left text-[12px] text-foreground transition-colors hover:bg-raised"
                        >
                          <span className="truncate">{p.name}</span>
                          {"similarity" in p && (
                            <span className="font-mono text-[10px] text-brand">
                              {Math.round(
                                ((p as unknown as Record<string, number>).similarity ?? 0) * 100
                              )}
                              %
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
            <div className="relative flex flex-1 flex-col overflow-hidden">
              {error && (
                <div className="border-b border-red-500/30 bg-red-500/10 px-4 py-2 text-[13px] text-red-500">
                  {error}
                  <button
                    onClick={() => setError("")}
                    className="ml-2 text-red-500 hover:text-red-400"
                  >
                    &times;
                  </button>
                </div>
              )}

              {selectedPage && (
                <div className="pointer-events-none absolute right-5 top-3 z-10 flex items-center gap-1.5 font-mono text-[10px] uppercase tracking-[0.08em] text-muted">
                  <span
                    className={
                      "h-1.5 w-1.5 rounded-full " +
                      (saveStatus === "saved" ? "bg-[#22C55E]" : "bg-[#EAB308]")
                    }
                  />
                  {saveStatus === "saving"
                    ? "saving"
                    : saveStatus === "dirty"
                    ? "unsaved"
                    : "saved"}
                </div>
              )}

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
                      pageIndex={workspacePages}
                      onNavigateInternal={handleNavigateInternal}
                    />

                    {/* Backlinks */}
                    {backlinks.length > 0 && (
                      <div className="mx-auto w-full max-w-[820px] px-12 pb-12">
                        <div className="mt-4 border-t border-border-subtle pt-6">
                          <p className="mb-3 font-mono text-[11px] font-medium uppercase tracking-[0.12em] text-muted">
                            Backlinks
                          </p>
                          <div className="flex flex-col gap-2">
                            {backlinks.map((bl) => (
                              <button
                                key={bl.id}
                                onClick={() => handleSelectPage(bl.id)}
                                className="flex items-center justify-between rounded-md border border-border-subtle px-3 py-2.5 text-left transition-colors hover:border-brand"
                              >
                                <span className="text-[13px] font-medium text-foreground">
                                  {bl.name}
                                </span>
                                <span className="font-mono text-[11px] text-muted">
                                  linked
                                </span>
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

      </div>
    </AppShell>
  );
}
