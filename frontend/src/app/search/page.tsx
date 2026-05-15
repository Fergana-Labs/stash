"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useCallback, useEffect, useMemo, useState } from "react";
import AppShell from "../../components/AppShell";
import { useAuth } from "../../hooks/useAuth";
import {
  getWorkspaceSidebar,
  getPublicStash,
  listStashes,
  listMyWorkspaces,
  searchWorkspaceEvents,
  searchWorkspacePages,
  type PublicStashDetail,
  type WorkspaceHistoryEvent,
  type WorkspaceSidebar,
  type WorkspaceStash,
  type WorkspaceFolder,
} from "../../lib/api";
import type { Page, Workspace } from "../../lib/types";

type ContentScope = "all" | "sessions" | "pages" | "stashes";

interface SearchResult {
  id: string;
  kind: "Session" | "Page" | "Stash";
  title: string;
  href: string;
  sourceName: string;
  detail: string;
  updatedAt: string;
}

interface SearchableStash extends WorkspaceStash {
  workspace_name: string;
}

const CONTENT_SCOPES: { id: ContentScope; label: string }[] = [
  { id: "all", label: "All" },
  { id: "sessions", label: "Sessions" },
  { id: "pages", label: "Pages" },
  { id: "stashes", label: "Stashes" },
];

export default function SearchPage() {
  return (
    <Suspense
      fallback={<div className="flex min-h-screen items-center justify-center text-muted">Loading...</div>}
    >
      <SearchPageInner />
    </Suspense>
  );
}

function SearchPageInner() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const { user, loading, logout } = useAuth();
  const [workspaces, setWorkspaces] = useState<Workspace[]>([]);
  const [workspaceStashes, setWorkspaceStashes] = useState<SearchableStash[]>([]);
  const [sidebars, setSidebars] = useState<Record<string, WorkspaceSidebar>>({});
  const [selectedWorkspaceId, setSelectedWorkspaceId] = useState(
    searchParams.get("workspace") ?? ""
  );
  const [selectedProductStashId, setSelectedProductStashId] = useState("");
  const [selectedFolderId, setSelectedFolderId] = useState("");
  const [selectedPageId, setSelectedPageId] = useState("");
  const [contentScope, setContentScope] = useState<ContentScope>("all");
  const [internalOnly, setInternalOnly] = useState(false);
  const [query, setQuery] = useState(searchParams.get("q") ?? "");
  const [results, setResults] = useState<SearchResult[]>([]);
  const [searchedQuery, setSearchedQuery] = useState("");
  const [fetching, setFetching] = useState(true);
  const [searching, setSearching] = useState(false);
  const [error, setError] = useState("");

  const loadWorkspaceData = useCallback(async () => {
    setFetching(true);
    setError("");
    try {
      const data = await listMyWorkspaces();
      const stashGroups = await Promise.all(
        data.workspaces.map(async (workspace) => {
          const workspaceStashes = await listStashes(workspace.id);
          return workspaceStashes.map((stash) => ({ ...stash, workspace_name: workspace.name }));
        })
      );
      setWorkspaces(data.workspaces);
      setWorkspaceStashes(stashGroups.flat());
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load workspace data");
    } finally {
      setFetching(false);
    }
  }, []);

  useEffect(() => {
    if (user) loadWorkspaceData();
  }, [user, loadWorkspaceData]);

  useEffect(() => {
    if (!selectedWorkspaceId || sidebars[selectedWorkspaceId]) return;

    let cancelled = false;
    getWorkspaceSidebar(selectedWorkspaceId)
      .then((sidebar) => {
        if (!cancelled) setSidebars((current) => ({ ...current, [selectedWorkspaceId]: sidebar }));
      })
      .catch((err) => {
        if (!cancelled) setError(err instanceof Error ? err.message : "Failed to load folders");
      });

    return () => {
      cancelled = true;
    };
  }, [selectedWorkspaceId, sidebars]);

  useEffect(() => {
    setSelectedFolderId("");
    setSelectedPageId("");
    setSelectedProductStashId("");
  }, [selectedWorkspaceId]);

  useEffect(() => {
    if (!loading && !user) router.push("/login");
  }, [user, loading, router]);

  const searchedWorkspaces = useMemo(() => {
    return selectedWorkspaceId
      ? workspaces.filter((workspace) => workspace.id === selectedWorkspaceId)
      : workspaces;
  }, [selectedWorkspaceId, workspaces]);

  const searchedStashes = useMemo(() => {
    const workspaceIds = new Set(searchedWorkspaces.map((workspace) => workspace.id));
    return workspaceStashes.filter((stash) => {
      if (internalOnly && stash.is_external) return false;
      const containerWorkspaceId = stash.added_to_workspace_id ?? stash.workspace_id;
      return workspaceIds.has(containerWorkspaceId);
    });
  }, [internalOnly, searchedWorkspaces, workspaceStashes]);

  const selectedProductStash = useMemo(
    () => searchedStashes.find((stash) => stash.id === selectedProductStashId) ?? null,
    [searchedStashes, selectedProductStashId]
  );

  useEffect(() => {
    if (!selectedProductStashId) return;
    if (selectedProductStash) return;
    setSelectedProductStashId("");
  }, [selectedProductStash, selectedProductStashId]);

  useEffect(() => {
    setSelectedFolderId("");
    setSelectedPageId("");
  }, [selectedProductStashId]);

  const folderOptions = useMemo(() => {
    if (!selectedWorkspaceId) return [];
    return sidebars[selectedWorkspaceId]?.files.folders ?? [];
  }, [selectedWorkspaceId, sidebars]);

  const pageOptions = useMemo(() => {
    if (!selectedWorkspaceId) return [];
    return sidebars[selectedWorkspaceId]?.files.pages ?? [];
  }, [selectedWorkspaceId, sidebars]);

  const handleSearch = useCallback(async () => {
    const q = query.trim();
    if (!q) return;

    setSearching(true);
    setError("");
    setSearchedQuery(q);
    try {
      const nextResults: SearchResult[] = [];
      const includeSessions = contentScope === "all" || contentScope === "sessions";
      const includePages = contentScope === "all" || contentScope === "pages";
      const includeStashes = contentScope === "all" || contentScope === "stashes";

      if (selectedProductStash) {
        const detail = await getPublicStash(selectedProductStash.slug);
        if (includeStashes) {
          nextResults.push(...searchStashes([selectedProductStash], q));
        }
        nextResults.push(
          ...searchPublicStashItems(detail, q, {
            includePages,
            includeSessions,
          })
        );
        setResults(sortResults(nextResults));
        return;
      }

      if (includeStashes && !selectedFolderId && !selectedPageId) {
        nextResults.push(...searchStashes(searchedStashes, q));
      }

      if (includeSessions && !selectedFolderId && !selectedPageId) {
        const settledSessionGroups = await Promise.allSettled(
          searchedWorkspaces.map(async (workspace) => ({
            workspace,
            events: await searchWorkspaceEvents(workspace.id, q, 100),
          }))
        );
        const sessionGroups = settledSessionGroups
          .filter((result) => result.status === "fulfilled")
          .map((result) => result.value);
        nextResults.push(...searchSessionsFromEvents(sessionGroups, q));
        if (sessionGroups.length < searchedWorkspaces.length) {
          setError("Session search is unavailable for one or more workspaces.");
        }
      }

      if (includePages) {
        const settledPageGroups = await Promise.allSettled(
          searchedWorkspaces.map(async (workspace) => ({
            workspace,
            pages: await searchWorkspacePages(workspace.id, q, 50),
          }))
        );
        const pageGroups = settledPageGroups
          .filter((result) => result.status === "fulfilled")
          .map((result) => result.value);
        const selectedSidebar = selectedWorkspaceId ? sidebars[selectedWorkspaceId] : undefined;
        const folderIds = selectedSidebar
          ? descendantFolderIds(selectedSidebar.files.folders, selectedFolderId)
          : new Set<string>();
        nextResults.push(
          ...searchPages(pageGroups, {
            selectedFolderId,
            selectedPageId,
            folderIds,
          })
        );
        if (pageGroups.length < searchedWorkspaces.length) {
          setError("Page search is unavailable for one or more workspaces.");
        }
      }

      setResults(sortResults(nextResults));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Search failed");
      setResults([]);
    } finally {
      setSearching(false);
    }
  }, [
    contentScope,
    query,
    searchedStashes,
    searchedWorkspaces,
    selectedFolderId,
    selectedPageId,
    selectedProductStash,
    selectedWorkspaceId,
    sidebars,
  ]);

  useEffect(() => {
    if (!searchParams.get("q")) return;
    if (fetching) return;
    handleSearch();
  }, [fetching, handleSearch, searchParams]);

  if (loading) {
    return <div className="flex min-h-screen items-center justify-center text-muted">Loading...</div>;
  }
  if (!user) return null;

  return (
    <AppShell user={user} onLogout={logout}>
      <div className="mx-auto w-full max-w-[1180px] px-6 py-8">
        <header className="border-b border-border-subtle pb-6">
          <p className="font-mono text-[11px] font-medium uppercase tracking-[0.14em] text-muted">
            Search
          </p>
          <h1 className="mt-3 font-display text-[34px] font-bold tracking-tight text-foreground">
            Search pages, sessions, and Stashes.
          </h1>
          <p className="mt-2 max-w-[700px] text-[14.5px] leading-relaxed text-muted">
            Search one workspace, one Stash, a folder inside a workspace, or
            internal knowledge only. Stash results are published bundles created from
            workspace pages and sessions.
          </p>
        </header>

        <div className="mt-6 grid gap-5 lg:grid-cols-[280px_minmax(0,1fr)]">
          <aside className="rounded-lg border border-border bg-surface p-4">
            <div className="flex flex-col gap-4">
              <label className="flex flex-col gap-1.5">
                <span className="text-[12px] font-medium text-foreground">Workspace</span>
                <select
                  value={selectedWorkspaceId}
                  onChange={(event) => setSelectedWorkspaceId(event.target.value)}
                  className="rounded-md border border-border bg-base px-2 py-2 text-[13px] text-foreground focus:border-brand focus:outline-none"
                >
                  <option value="">All workspaces</option>
                  {workspaces.map((workspace) => (
                    <option key={workspace.id} value={workspace.id}>
                      {workspace.name}
                    </option>
                  ))}
                </select>
              </label>

              <label className="flex flex-col gap-1.5">
                <span className="text-[12px] font-medium text-foreground">Stash</span>
                <select
                  value={selectedProductStashId}
                  onChange={(event) => setSelectedProductStashId(event.target.value)}
                  className="rounded-md border border-border bg-base px-2 py-2 text-[13px] text-foreground focus:border-brand focus:outline-none"
                >
                  <option value="">All Stashes</option>
                  {searchedStashes.map((stash) => (
                    <option key={stash.id} value={stash.id}>
                      {stash.title}
                      {stash.is_external ? " (External)" : ""}
                    </option>
                  ))}
                </select>
              </label>

              <label className="flex flex-col gap-1.5">
                <span className="text-[12px] font-medium text-foreground">Folder</span>
                <select
                  value={selectedFolderId}
                  onChange={(event) => {
                    setSelectedFolderId(event.target.value);
                    if (event.target.value) setSelectedPageId("");
                  }}
                  disabled={!selectedWorkspaceId || Boolean(selectedProductStashId || selectedPageId)}
                  className="rounded-md border border-border bg-base px-2 py-2 text-[13px] text-foreground focus:border-brand focus:outline-none disabled:opacity-50"
                >
                  <option value="">
                    {selectedProductStashId ? "Stash selected" : "Entire workspace"}
                  </option>
                  {folderOptions.map((folder) => (
                    <option key={folder.id} value={folder.id}>
                      {folder.name}
                    </option>
                  ))}
                </select>
              </label>

              <label className="flex flex-col gap-1.5">
                <span className="text-[12px] font-medium text-foreground">Page</span>
                <select
                  value={selectedPageId}
                  onChange={(event) => {
                    setSelectedPageId(event.target.value);
                    if (event.target.value) setSelectedFolderId("");
                  }}
                  disabled={!selectedWorkspaceId || Boolean(selectedProductStashId || selectedFolderId)}
                  className="rounded-md border border-border bg-base px-2 py-2 text-[13px] text-foreground focus:border-brand focus:outline-none disabled:opacity-50"
                >
                  <option value="">
                    {selectedProductStashId
                      ? "Stash selected"
                      : selectedFolderId
                        ? "Folder selected"
                        : "Any page"}
                  </option>
                  {pageOptions.map((page) => (
                    <option key={page.id} value={page.id}>
                      {page.name}
                    </option>
                  ))}
                </select>
              </label>

              <div>
                <span className="text-[12px] font-medium text-foreground">Content</span>
                <div className="mt-2 grid grid-cols-2 gap-1 rounded-md border border-border bg-base p-1">
                  {CONTENT_SCOPES.map((scope) => (
                    <button
                      key={scope.id}
                      type="button"
                      onClick={() => setContentScope(scope.id)}
                      className={
                        "rounded px-2 py-1 text-[12px] " +
                        (contentScope === scope.id
                          ? "bg-[var(--color-brand-600)] text-white"
                          : "text-muted hover:bg-raised hover:text-foreground")
                      }
                    >
                      {scope.label}
                    </button>
                  ))}
                </div>
              </div>

              <label className="flex items-center gap-2 text-[13px] text-foreground">
                <input
                  type="checkbox"
                  checked={internalOnly}
                  onChange={(event) => setInternalOnly(event.target.checked)}
                  className="accent-[var(--color-brand-600)]"
                />
                Internal only
              </label>
            </div>
          </aside>

          <main className="min-w-0">
            <form
              onSubmit={(event) => {
                event.preventDefault();
                handleSearch();
              }}
              className="flex items-center gap-3 rounded-lg border border-border bg-surface px-3 py-2 focus-within:border-brand"
            >
              <input
                type="text"
                placeholder="Search for a decision, transcript, Stash, or page..."
                value={query}
                onChange={(event) => setQuery(event.target.value)}
                className="min-w-0 flex-1 bg-transparent text-[15px] text-foreground placeholder:text-muted focus:outline-none"
                autoFocus
              />
              <button
                type="submit"
                disabled={searching || !query.trim() || fetching}
                className="rounded-md bg-[var(--color-brand-600)] px-3 py-1.5 text-[13px] font-medium text-white hover:bg-[var(--color-brand-700)] disabled:opacity-50"
              >
                {searching ? "Searching..." : "Search"}
              </button>
            </form>

            {error && (
              <div className="mt-4 rounded-md border border-red-300 bg-red-50 px-3 py-2 text-[13px] text-red-700">
                {error}
              </div>
            )}

            {searching && (
              <p className="py-10 text-center text-[13px] text-muted">
                Searching selected knowledge...
              </p>
            )}

            {!searching && searchedQuery && results.length === 0 && !error && (
              <p className="py-10 text-center text-[13px] text-muted">
                No results found for &ldquo;{searchedQuery}&rdquo;.
              </p>
            )}

            {!searching && results.length > 0 && (
              <section className="mt-5">
                <div className="mb-3 flex items-center justify-between gap-3">
                  <h2 className="font-display text-[18px] font-semibold text-foreground">
                    Results
                  </h2>
                  <p className="font-mono text-[11px] uppercase tracking-[0.12em] text-muted">
                    {results.length}
                  </p>
                </div>
                <div className="flex flex-col gap-2">
                  {results.map((result) => (
                    <Link
                      key={`${result.kind}:${result.id}`}
                      href={result.href}
                      className="rounded-lg border border-border bg-base px-4 py-3 transition hover:border-[var(--color-brand-300)] hover:bg-[var(--color-brand-50)]"
                    >
                      <div className="flex items-start justify-between gap-3">
                        <div className="min-w-0">
                          <div className="flex items-center gap-2">
                            <span className="rounded-md border border-border-subtle px-1.5 py-0.5 text-[10px] uppercase tracking-wide text-muted">
                              {result.kind}
                            </span>
                            <h3 className="truncate text-[14px] font-semibold text-foreground">
                              {result.title}
                            </h3>
                          </div>
                          <p className="mt-1 line-clamp-2 text-[13px] leading-relaxed text-muted">
                            {result.detail}
                          </p>
                        </div>
                        <div className="shrink-0 text-right text-[11px] text-muted">
                          <div>{result.sourceName}</div>
                          <div>{relativeTime(result.updatedAt)}</div>
                        </div>
                      </div>
                    </Link>
                  ))}
                </div>
              </section>
            )}
          </main>
        </div>
      </div>
    </AppShell>
  );
}

function searchStashes(stashes: SearchableStash[], query: string): SearchResult[] {
  const q = query.toLowerCase();
  return stashes
    .filter((stash) => {
      const text = [stash.title, stash.description, stash.workspace_name]
        .filter(Boolean)
        .join(" ")
        .toLowerCase();
      return text.includes(q);
    })
    .map((stash) => ({
      id: stash.id,
      kind: "Stash" as const,
      title: stash.title,
      href: `/stashes/${stash.slug}`,
      sourceName: stash.workspace_name,
      detail:
        (stash.is_external ? "External Stash" : "Stash") +
        ` / ${stash.description || `${stash.items.length} items`}`,
      updatedAt: stash.updated_at,
    }));
}

function searchSessionsFromEvents(
  groups: { workspace: Workspace; events: WorkspaceHistoryEvent[] }[],
  query: string
): SearchResult[] {
  const resultsBySession = new Map<string, SearchResult>();
  for (const { workspace, events } of groups) {
    for (const event of events) {
      if (!event.session_id) continue;
      const id = `${workspace.id}:${event.session_id}`;
      const existing = resultsBySession.get(id);
      if (existing && new Date(existing.updatedAt) >= new Date(event.created_at)) continue;
      resultsBySession.set(id, {
        id,
        kind: "Session",
        title: event.session_id,
        href: `/workspaces/${workspace.id}/sessions/${encodeURIComponent(event.session_id)}`,
        sourceName: workspace.name,
        detail: sessionSearchSnippet(event, query),
        updatedAt: event.created_at,
      });
    }
  }
  return [...resultsBySession.values()];
}

function sessionSearchSnippet(event: WorkspaceHistoryEvent, query: string): string {
  const content = event.content.trim();
  if (!content) return `${event.agent_name || "agent"} / ${event.event_type}`;

  const lower = content.toLowerCase();
  const index = lower.indexOf(query.toLowerCase());
  if (index === -1) return content.slice(0, 220);

  const start = Math.max(0, index - 80);
  const end = Math.min(content.length, index + query.length + 140);
  const prefix = start > 0 ? "..." : "";
  const suffix = end < content.length ? "..." : "";
  return `${prefix}${content.slice(start, end)}${suffix}`;
}

function searchPages(
  groups: { workspace: Workspace; pages: Page[] }[],
  scope: {
    selectedFolderId: string;
    selectedPageId: string;
    folderIds: Set<string>;
  }
): SearchResult[] {
  return groups.flatMap(({ workspace, pages }) =>
    pages
      .filter((page) => {
        if (scope.selectedPageId) return page.id === scope.selectedPageId;
        if (!scope.selectedFolderId) return true;
        return Boolean(page.folder_id && scope.folderIds.has(page.folder_id));
      })
      .map((page) => ({
        id: page.id,
        kind: "Page" as const,
        title: page.name,
        href: `/workspaces/${workspace.id}/p/${page.id}`,
        sourceName: workspace.name,
        detail:
          page.content_type === "html"
            ? stripHtml(page.content_html).slice(0, 220) || "HTML page"
            : page.content_markdown?.slice(0, 220) || "Markdown page",
        updatedAt: page.updated_at,
      }))
  );
}

function descendantFolderIds(
  folders: WorkspaceFolder[],
  selectedFolderId: string
): Set<string> {
  if (!selectedFolderId) return new Set();

  const childrenByParent = new Map<string, WorkspaceFolder[]>();
  for (const folder of folders) {
    if (!folder.parent_folder_id) continue;
    const children = childrenByParent.get(folder.parent_folder_id) ?? [];
    children.push(folder);
    childrenByParent.set(folder.parent_folder_id, children);
  }

  const ids = new Set<string>([selectedFolderId]);
  const queue = [selectedFolderId];
  while (queue.length > 0) {
    const current = queue.shift()!;
    for (const child of childrenByParent.get(current) ?? []) {
      ids.add(child.id);
      queue.push(child.id);
    }
  }
  return ids;
}

function searchPublicStashItems(
  detail: PublicStashDetail,
  query: string,
  scope: { includePages: boolean; includeSessions: boolean }
): SearchResult[] {
  const q = query.toLowerCase();
  return detail.items.flatMap((item, index) => {
    if (item.object_type === "folder" && scope.includePages) {
      return searchPublicFolder(detail, item, index, q);
    }
    if (item.object_type === "page" && scope.includePages) {
      return searchPublicPage(detail, item, index, q);
    }
    if (item.object_type === "session" && scope.includeSessions) {
      return searchPublicSession(detail, item, index, q);
    }
    return [];
  });
}

function searchPublicFolder(
  detail: PublicStashDetail,
  item: PublicStashDetail["items"][number],
  index: number,
  query: string
): SearchResult[] {
  const inline = item.inline as {
    pages?: {
      id: string;
      name: string;
      content_markdown?: string | null;
      content_html?: string | null;
      updated_at?: string | null;
    }[];
  };

  return (inline.pages ?? [])
    .filter((page) => textIncludes(query, page.name, page.content_markdown, page.content_html))
    .map((page) => ({
      id: `${item.object_id}:${page.id}`,
      kind: "Page" as const,
      title: page.name,
      href: `/stashes/${detail.stash.slug}#item-${index}`,
      sourceName: detail.stash.title,
      detail: pageSnippet(page.content_markdown, page.content_html),
      updatedAt: page.updated_at || detail.stash.updated_at,
    }));
}

function searchPublicPage(
  detail: PublicStashDetail,
  item: PublicStashDetail["items"][number],
  index: number,
  query: string
): SearchResult[] {
  const inline = item.inline as {
    page?: {
      id: string;
      name: string;
      content_markdown?: string | null;
      content_html?: string | null;
      updated_at?: string | null;
    };
  };
  const page = inline.page;
  if (!page) return [];
  if (!textIncludes(query, page.name, page.content_markdown, page.content_html)) return [];

  return [
    {
      id: item.object_id,
      kind: "Page" as const,
      title: page.name,
      href: `/stashes/${detail.stash.slug}#item-${index}`,
      sourceName: detail.stash.title,
      detail: pageSnippet(page.content_markdown, page.content_html),
      updatedAt: page.updated_at || detail.stash.updated_at,
    },
  ];
}

function searchPublicSession(
  detail: PublicStashDetail,
  item: PublicStashDetail["items"][number],
  index: number,
  query: string
): SearchResult[] {
  const inline = item.inline as {
    session?: {
      id?: string;
      session_id: string;
      agent_name?: string | null;
      summary?: string | null;
      started_at?: string | null;
      finished_at?: string | null;
      events?: {
        event_type: string;
        tool_name?: string | null;
        content: string;
        created_at: string;
      }[];
    };
  };
  const session = inline.session;
  if (!session) return [];

  const eventText = (session.events ?? [])
    .map((event) => [event.event_type, event.tool_name, event.content].filter(Boolean).join(" "))
    .join(" ");
  if (!textIncludes(query, session.session_id, session.agent_name, session.summary, eventText)) {
    return [];
  }

  return [
    {
      id: session.id || item.object_id,
      kind: "Session" as const,
      title: session.summary || session.session_id,
      href: `/stashes/${detail.stash.slug}#item-${index}`,
      sourceName: detail.stash.title,
      detail: sessionSnippet(session),
      updatedAt: session.finished_at || session.started_at || detail.stash.updated_at,
    },
  ];
}

function textIncludes(query: string, ...values: (string | null | undefined)[]): boolean {
  return values
    .filter(Boolean)
    .join(" ")
    .toLowerCase()
    .includes(query);
}

function pageSnippet(markdown?: string | null, html?: string | null): string {
  if (markdown?.trim()) return markdown.slice(0, 220);
  if (html?.trim()) return stripHtml(html).slice(0, 220);
  return "Page in this Stash";
}

function sessionSnippet(session: {
  agent_name?: string | null;
  summary?: string | null;
  events?: { event_type: string; tool_name?: string | null; content: string }[];
}): string {
  if (session.summary?.trim()) return session.summary.slice(0, 220);
  const firstEvent = session.events?.find((event) => event.content.trim());
  if (!firstEvent) return `${session.agent_name || "Agent"} session in this Stash`;
  return firstEvent.content.slice(0, 220);
}

function sortResults(results: SearchResult[]): SearchResult[] {
  return [...results].sort(
    (a, b) => new Date(b.updatedAt).getTime() - new Date(a.updatedAt).getTime()
  );
}

function stripHtml(html: string): string {
  return html.replace(/<[^>]*>/g, " ").replace(/\s+/g, " ").trim();
}

function relativeTime(iso: string): string {
  const ms = Date.now() - new Date(iso).getTime();
  if (ms < 60_000) return "just now";
  const minutes = Math.floor(ms / 60_000);
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.floor(hours / 24);
  if (days < 30) return `${days}d ago`;
  return new Date(iso).toLocaleDateString();
}
