"use client";

import { Suspense, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import AppShell from "../../components/AppShell";
import { useBreadcrumbs, type Crumb } from "../../components/BreadcrumbContext";
import FileTreeComponent from "../../components/workspace/FileTree";
import MarkdownEditor, { SaveStatus } from "../../components/workspace/MarkdownEditor";
import HtmlPageEditor from "../../components/workspace/HtmlPageEditor";
import AddToCollect from "../../components/share/AddToCollect";
import { useSetShareTarget } from "../../components/share/ShareTargetContext";
import { useAuth } from "../../hooks/useAuth";
import {
  createFolder,
  createPage,
  deleteFolder,
  deletePage,
  getPage,
  getBacklinks,
  getWorkspaceTree,
  listWorkspacePages,
  semanticSearchPages,
  updateFolder,
  updatePage,
  WorkspacePageEntry,
} from "../../lib/api";
import {
  FolderTreeNode,
  Page,
  PageLink,
  WorkspaceTree,
} from "../../lib/types";
import { listMyWorkspaces } from "../../lib/api";

export default function WikiPage() {
  return (
    <Suspense fallback={<div className="min-h-screen flex items-center justify-center text-muted">Loading...</div>}>
      <WikiPageInner />
    </Suspense>
  );
}

interface WorkspaceOption {
  id: string;
  name: string;
}

const EMPTY_TREE: WorkspaceTree = { folders: [], pages: [] };

// Walks the folder tree; returns the path of folder names from the root down
// to (and including) the folder containing the given page, or [] if the page
// sits at the workspace root or isn't in this tree.
function findFolderPathForPage(tree: WorkspaceTree, pageId: string): string[] {
  function walk(folders: FolderTreeNode[], trail: string[]): string[] | null {
    for (const f of folders) {
      const next = [...trail, f.name];
      if (f.pages.some((p) => p.id === pageId)) return next;
      const sub = walk(f.folders, next);
      if (sub) return sub;
    }
    return null;
  }
  return walk(tree.folders, []) ?? [];
}

function WikiPageInner() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const wsId = searchParams.get("ws");
  const pageParam = searchParams.get("page");
  const { user, loading, logout } = useAuth();

  const [workspaces, setWorkspaces] = useState<WorkspaceOption[]>([]);
  const [tree, setTree] = useState<WorkspaceTree>(EMPTY_TREE);
  const [selectedPageId, setSelectedPageId] = useState<string | null>(null);
  const [selectedPage, setSelectedPage] = useState<Page | null>(null);
  const [backlinks, setBacklinks] = useState<PageLink[]>([]);
  // Flat workspace page index — drives `[[` autocomplete and click-to-navigate.
  const [workspacePages, setWorkspacePages] = useState<WorkspacePageEntry[]>([]);

  const [saveStatus, setSaveStatus] = useState<SaveStatus>("saved");
  const [semanticQuery, setSemanticQuery] = useState("");
  const [semanticResults, setSemanticResults] = useState<Page[]>([]);
  const [semanticSearching, setSemanticSearching] = useState(false);
  const [error, setError] = useState("");
  const [deepLinkedPage, setDeepLinkedPage] = useState(false);

  const loadWorkspaces = useCallback(async () => {
    try {
      const data = await listMyWorkspaces();
      setWorkspaces(
        (data.workspaces ?? []).map((w: { id: string; name: string }) => ({
          id: w.id,
          name: w.name,
        }))
      );
    } catch {
      /* ignore */
    }
  }, []);

  useEffect(() => {
    if (user) loadWorkspaces();
  }, [user, loadWorkspaces]);

  const activeWorkspace = useMemo(
    () => workspaces.find((w) => w.id === wsId) ?? null,
    [workspaces, wsId]
  );

  const loadTree = useCallback(async (workspaceId: string) => {
    try {
      const t = await getWorkspaceTree(workspaceId);
      setTree(t);
    } catch {
      setTree(EMPTY_TREE);
    }
  }, []);

  const loadWorkspacePages = useCallback(async (workspaceId: string) => {
    try {
      const pages = await listWorkspacePages(workspaceId);
      setWorkspacePages(pages);
    } catch {
      setWorkspacePages([]);
    }
  }, []);

  // Reload tree + page index whenever the active workspace changes.
  const prevWsIdRef = useRef<string | null>(null);
  useEffect(() => {
    if (!wsId) {
      setTree(EMPTY_TREE);
      setWorkspacePages([]);
      setSelectedPageId(null);
      setSelectedPage(null);
      setBacklinks([]);
      prevWsIdRef.current = null;
      return;
    }
    if (prevWsIdRef.current === wsId) return;
    prevWsIdRef.current = wsId;
    setSelectedPageId(null);
    setSelectedPage(null);
    setBacklinks([]);
    setDeepLinkedPage(false);
    loadTree(wsId);
    loadWorkspacePages(wsId);
  }, [wsId, loadTree, loadWorkspacePages]);

  const handleSelectPage = useCallback(
    async (pageId: string) => {
      if (!wsId) return;
      setSelectedPageId(pageId);
      setBacklinks([]);
      try {
        const p = await getPage(wsId, pageId);
        setSelectedPage(p);
        try {
          const bl = await getBacklinks(wsId, pageId);
          setBacklinks(bl);
        } catch {
          /* backlinks are optional */
        }
      } catch {
        setError("Failed to load page");
      }
    },
    [wsId]
  );

  // Deep-link: select page from URL params once the workspace tree is available.
  useEffect(() => {
    if (deepLinkedPage) return;
    if (!pageParam || !wsId) {
      setDeepLinkedPage(true);
      return;
    }
    setDeepLinkedPage(true);
    handleSelectPage(pageParam);
  }, [deepLinkedPage, pageParam, wsId, handleSelectPage]);

  // Sync the URL with the current selection (?ws=...&page=...).
  useEffect(() => {
    if (typeof window === "undefined") return;
    const current = new URL(window.location.href);
    const currentPage = current.searchParams.get("page");
    if (currentPage === (selectedPageId ?? null)) return;
    const url = new URL(window.location.href);
    if (selectedPageId) url.searchParams.set("page", selectedPageId);
    else url.searchParams.delete("page");
    window.history.pushState({}, "", url.toString());
  }, [selectedPageId]);

  useEffect(() => {
    if (typeof window === "undefined") return;
    const onPop = () => {
      const p = new URL(window.location.href).searchParams;
      const pid = p.get("page");
      if (pid && pid !== selectedPageId) {
        setSelectedPageId(pid);
        if (wsId) {
          getPage(wsId, pid)
            .then(setSelectedPage)
            .catch(() => undefined);
        }
      } else if (!pid && selectedPageId) {
        setSelectedPageId(null);
        setSelectedPage(null);
      }
    };
    window.addEventListener("popstate", onPop);
    return () => window.removeEventListener("popstate", onPop);
  }, [selectedPageId, wsId]);

  // Editor → wiki link click handler.
  const handleNavigateInternal = useCallback(
    async (href: string) => {
      const url = new URL(href, window.location.origin);
      if (url.pathname !== "/wiki") {
        router.push(`${url.pathname}${url.search}`);
        return;
      }
      const targetWs = url.searchParams.get("ws");
      const targetPage = url.searchParams.get("page");
      if (!targetPage) return;
      if (targetWs && targetWs !== wsId) {
        router.push(`/wiki?ws=${targetWs}&page=${targetPage}`);
        return;
      }
      handleSelectPage(targetPage);
    },
    [router, wsId, handleSelectPage]
  );

  const folderPath = useMemo(
    () => (selectedPage ? findFolderPathForPage(tree, selectedPage.id) : []),
    [selectedPage, tree]
  );

  const handleSemanticSearch = useCallback(async () => {
    if (!wsId || !semanticQuery.trim()) return;
    setSemanticSearching(true);
    try {
      const pages = await semanticSearchPages(wsId, semanticQuery.trim());
      setSemanticResults(pages);
    } catch {
      setSemanticResults([]);
    }
    setSemanticSearching(false);
  }, [wsId, semanticQuery]);

  const handleCreatePage = useCallback(
    async (folderId: string | null) => {
      if (!wsId) return;
      const name = prompt("Page name:");
      if (!name) return;
      const typeRaw = (prompt("Page type — 'markdown' or 'html':", "markdown") || "markdown")
        .trim()
        .toLowerCase();
      const content_type: "markdown" | "html" = typeRaw === "html" ? "html" : "markdown";
      try {
        const p = await createPage(wsId, name, folderId, undefined, { content_type });
        await loadTree(wsId);
        await loadWorkspacePages(wsId);
        setSelectedPageId(p.id);
        setSelectedPage(p);
      } catch (err) {
        setError(err instanceof Error ? err.message : "Failed to create page");
      }
    },
    [wsId, loadTree, loadWorkspacePages]
  );

  const handleCreateFolder = useCallback(
    async (parentFolderId: string | null) => {
      if (!wsId) return;
      const name = prompt("Folder name:");
      if (!name) return;
      try {
        await createFolder(wsId, name, parentFolderId);
        await loadTree(wsId);
      } catch (err) {
        setError(err instanceof Error ? err.message : "Failed to create folder");
      }
    },
    [wsId, loadTree]
  );

  const handleDeletePage = useCallback(
    async (pageId: string) => {
      if (!wsId || !confirm("Delete this page?")) return;
      try {
        await deletePage(wsId, pageId);
        if (selectedPageId === pageId) {
          setSelectedPageId(null);
          setSelectedPage(null);
        }
        await loadTree(wsId);
        await loadWorkspacePages(wsId);
      } catch (err) {
        setError(err instanceof Error ? err.message : "Failed to delete");
      }
    },
    [wsId, selectedPageId, loadTree, loadWorkspacePages]
  );

  const handleDeleteFolder = useCallback(
    async (folderId: string) => {
      if (!wsId || !confirm("Delete this folder and everything inside it?")) return;
      try {
        await deleteFolder(wsId, folderId);
        setSelectedPageId(null);
        setSelectedPage(null);
        await loadTree(wsId);
        await loadWorkspacePages(wsId);
      } catch (err) {
        setError(err instanceof Error ? err.message : "Failed to delete folder");
      }
    },
    [wsId, loadTree, loadWorkspacePages]
  );

  const handleRenamePage = useCallback(
    async (pageId: string, currentName: string) => {
      if (!wsId) return;
      const name = prompt("New name:", currentName);
      if (!name || name === currentName) return;
      try {
        const updated = await updatePage(wsId, pageId, { name });
        if (selectedPageId === pageId) setSelectedPage(updated);
        await loadTree(wsId);
        await loadWorkspacePages(wsId);
      } catch (err) {
        setError(err instanceof Error ? err.message : "Failed to rename");
      }
    },
    [wsId, selectedPageId, loadTree, loadWorkspacePages]
  );

  const handleInlineRename = useCallback(
    async (name: string) => {
      if (!wsId || !selectedPageId) return;
      try {
        const updated = await updatePage(wsId, selectedPageId, { name });
        setSelectedPage(updated);
        await loadTree(wsId);
        await loadWorkspacePages(wsId);
      } catch {
        /* silent */
      }
    },
    [wsId, selectedPageId, loadTree, loadWorkspacePages]
  );

  const handleRenameFolder = useCallback(
    async (folderId: string, currentName: string) => {
      if (!wsId) return;
      const name = prompt("New name:", currentName);
      if (!name || name === currentName) return;
      try {
        await updateFolder(wsId, folderId, { name });
        await loadTree(wsId);
      } catch (err) {
        setError(err instanceof Error ? err.message : "Failed to rename folder");
      }
    },
    [wsId, loadTree]
  );

  const handleMovePage = useCallback(
    async (pageId: string, folderId: string | null) => {
      if (!wsId) return;
      try {
        const data = folderId ? { folder_id: folderId } : { move_to_root: true };
        const updated = await updatePage(wsId, pageId, data);
        if (selectedPageId === pageId) setSelectedPage(updated);
        await loadTree(wsId);
        await loadWorkspacePages(wsId);
      } catch (err) {
        setError(err instanceof Error ? err.message : "Failed to move");
      }
    },
    [wsId, selectedPageId, loadTree, loadWorkspacePages]
  );

  const handleSavePage = useCallback(
    async (content: string) => {
      if (!wsId || !selectedPageId) return;
      try {
        await updatePage(wsId, selectedPageId, { content });
      } catch (err) {
        setError(err instanceof Error ? err.message : "Failed to save");
      }
    },
    [wsId, selectedPageId]
  );

  const handleSaveHtmlPage = useCallback(
    async (content_html: string) => {
      if (!wsId || !selectedPageId) return;
      try {
        await updatePage(wsId, selectedPageId, { content_html, content_type: "html" });
      } catch (err) {
        setError(err instanceof Error ? err.message : "Failed to save");
      }
    },
    [wsId, selectedPageId]
  );

  useEffect(() => {
    if (!loading && !user) router.push("/login");
  }, [user, loading, router]);

  // Crumbs: Wiki → workspace → folder chain → page name.
  const crumbs: Crumb[] = useMemo(() => {
    const base: Crumb[] = [{ label: "Wiki", href: "/wiki" }];
    if (activeWorkspace) {
      base.push({ label: activeWorkspace.name, href: `/wiki?ws=${activeWorkspace.id}` });
    }
    if (selectedPage) {
      for (const seg of folderPath) base.push({ label: seg });
      base.push({ label: selectedPage.name });
    }
    return base;
  }, [activeWorkspace, selectedPage, folderPath]);
  const depKey = `${activeWorkspace?.id ?? ""}:${folderPath.join("/")}:${selectedPage?.id ?? ""}:${selectedPage?.name ?? ""}`;
  useBreadcrumbs(crumbs, depKey);

  useSetShareTarget(
    selectedPage
      ? { objectType: "page", objectId: selectedPage.id, label: selectedPage.name }
      : null,
    `page:${selectedPage?.id ?? ""}:${selectedPage?.name ?? ""}`
  );

  if (loading)
    return (
      <div className="min-h-screen flex items-center justify-center text-muted">Loading...</div>
    );
  if (!user) return null;

  return (
    <AppShell user={user} onLogout={logout}>
      <div className="flex flex-col h-full overflow-hidden">
        {!wsId && (
          /* Workspace picker */
          <div className="flex-1 overflow-y-auto">
            <div className="mx-auto w-full max-w-[1120px] px-8 pb-16 pt-8">
              <h1 className="mb-6 font-display text-[32px] font-bold tracking-[-0.02em] text-foreground">
                Wiki
              </h1>
              <p className="mb-6 text-[13px] text-muted">
                Pick a workspace to open its wiki.
              </p>
              <div className="flex flex-col gap-2">
                {workspaces.length === 0 ? (
                  <p className="text-[13px] text-muted">No workspaces yet.</p>
                ) : (
                  workspaces.map((w) => (
                    <button
                      key={w.id}
                      onClick={() => router.push(`/wiki?ws=${w.id}`)}
                      className="flex w-full items-center gap-3 rounded-lg border border-border-subtle bg-base px-4 py-3.5 text-left transition-colors hover:border-brand"
                    >
                      <div className="flex h-8 w-8 flex-shrink-0 items-center justify-center rounded-md bg-raised font-mono text-[12px] font-bold text-muted">
                        W
                      </div>
                      <div className="min-w-0 flex-1 text-[14px] font-semibold text-foreground">
                        {w.name}
                      </div>
                      <span className="font-mono text-[11px] text-muted">→</span>
                    </button>
                  ))
                )}
              </div>
            </div>
          </div>
        )}

        {wsId && (
          <div className="flex flex-1 overflow-hidden">
            {/* Sidebar: workspace tree */}
            <div className="flex w-[280px] flex-shrink-0 flex-col overflow-hidden border-r border-border bg-surface">
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
                      </button>
                    ))}
                  </div>
                )}
              </div>

              <div className="flex-1 overflow-hidden">
                <FileTreeComponent
                  tree={tree}
                  selectedPageId={selectedPageId}
                  onSelectPage={handleSelectPage}
                  onCreatePage={handleCreatePage}
                  onCreateFolder={handleCreateFolder}
                  onDeletePage={handleDeletePage}
                  onDeleteFolder={handleDeleteFolder}
                  onRenamePage={handleRenamePage}
                  onRenameFolder={handleRenameFolder}
                  onMovePage={handleMovePage}
                />
              </div>
            </div>

            {/* Editor */}
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
                <div className="absolute right-5 top-3 z-20 flex items-center gap-3">
                  <div className="pointer-events-none flex items-center gap-1.5 font-mono text-[10px] uppercase tracking-[0.08em] text-muted">
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
                  <AddToCollect
                    objectType="page"
                    objectId={selectedPage.id}
                    workspaceId={wsId}
                    label={selectedPage.name}
                  />
                </div>
              )}

              {selectedPage ? (
                <div className="flex-1 flex flex-col overflow-hidden">
                  <div className="flex-1 overflow-y-auto">
                    {selectedPage.content_type === "html" ? (
                      <div className="mx-auto w-full max-w-[1200px] px-6 py-4">
                        <HtmlPageEditor
                          key={selectedPage.id}
                          file={selectedPage}
                          onSave={handleSaveHtmlPage}
                          onSaveStatusChange={setSaveStatus}
                        />
                      </div>
                    ) : (
                      <MarkdownEditor
                        key={selectedPage.id}
                        workspaceId={wsId}
                        folderPath={folderPath}
                        file={selectedPage}
                        onSave={handleSavePage}
                        onSaveStatusChange={setSaveStatus}
                        onRename={handleInlineRename}
                        pageIndex={workspacePages}
                        onNavigateInternal={handleNavigateInternal}
                      />
                    )}

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
                                <span className="font-mono text-[11px] text-muted">linked</span>
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

