"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useCallback, useEffect, useMemo, useState } from "react";
import AppShell from "../../components/AppShell";
import CustomSelect from "../../components/CustomSelect";
import { BasicPageSkeleton, SearchResultsSkeleton, SearchSkeleton } from "../../components/SkeletonStates";
import { useAuth } from "../../hooks/useAuth";
import { track } from "../../lib/analytics";
import {
  getWorkspaceSidebar,
  getPublicSkill,
  getSessionEvents,
  listAllTables,
  listSharedSkills,
  listMyWorkspaces,
  searchWorkspaceEvents,
  searchWorkspacePages,
  type PublicSkillDetail,
  type SessionEvent,
  type WorkspaceHistoryEvent,
  type WorkspaceSidebar,
  type WorkspaceSkill,
  type WorkspaceFolder,
} from "../../lib/api";
import type { Page, TableWithWorkspace, Workspace } from "../../lib/types";

type ContentScope = "all" | "sessions" | "pages" | "tables" | "skills";

// Coarse buckets for analytics — actual counts have high cardinality
// and add no signal beyond "no results / few / many."
function bucketCount(n: number): string {
  if (n === 0) return "0";
  if (n < 5) return "1-4";
  if (n < 20) return "5-19";
  if (n < 100) return "20-99";
  return "100+";
}

interface SearchResult {
  id: string;
  kind: "Session" | "Page" | "Table" | "Skill";
  title: string;
  href: string;
  sourceName: string;
  detail: string;
  updatedAt: string;
  relevance: number;
}

interface SearchableSkill extends WorkspaceSkill {
  workspace_name: string;
}

const CONTENT_SCOPES: { id: ContentScope; label: string }[] = [
  { id: "all", label: "All" },
  { id: "sessions", label: "Sessions" },
  { id: "pages", label: "Pages" },
  { id: "skills", label: "Skills" },
  { id: "tables", label: "Tables" },
];

function initialContentScope(value: string | null, sessionId: string): ContentScope {
  if (sessionId) return "sessions";
  if (value === "sessions" || value === "pages" || value === "tables" || value === "skills") {
    return value;
  }
  return "all";
}

export default function SearchPage() {
  return (
    <Suspense
      fallback={<BasicPageSkeleton />}
    >
      <SearchPageInner />
    </Suspense>
  );
}

function SearchPageInner() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const { user, loading, logout } = useAuth();
  const initialSessionId = searchParams.get("session") ?? "";
  const [workspaces, setWorkspaces] = useState<Workspace[]>([]);
  const [workspaceSkills, setWorkspaceSkills] = useState<SearchableSkill[]>([]);
  const [sidebars, setSidebars] = useState<Record<string, WorkspaceSidebar>>({});
  const [selectedWorkspaceId, setSelectedWorkspaceId] = useState(
    searchParams.get("workspace") ?? ""
  );
  const [selectedProductSkillId, setSelectedProductSkillId] = useState("");
  const [selectedProductSkillSlug, setSelectedProductSkillSlug] = useState(
    searchParams.get("skill") ?? ""
  );
  const [selectedFolderId, setSelectedFolderId] = useState(searchParams.get("folder") ?? "");
  const [selectedPageId, setSelectedPageId] = useState(searchParams.get("page") ?? "");
  const [selectedSessionId, setSelectedSessionId] = useState(initialSessionId);
  const [contentScope, setContentScope] = useState<ContentScope>(
    () => initialContentScope(searchParams.get("content"), initialSessionId)
  );
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
      const skillGroups = await Promise.all(
        data.workspaces.map(async (workspace) => {
          const workspaceSkills = await listSharedSkills(workspace.id);
          return workspaceSkills.map((skill) => ({ ...skill, workspace_name: workspace.name }));
        })
      );
      setWorkspaces(data.workspaces);
      setWorkspaceSkills(skillGroups.flat());
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
    if (!loading && !user) router.push("/login");
  }, [user, loading, router]);

  const searchedWorkspaces = useMemo(() => {
    return selectedWorkspaceId
      ? workspaces.filter((workspace) => workspace.id === selectedWorkspaceId)
      : workspaces;
  }, [selectedWorkspaceId, workspaces]);

  const searchedSkills = useMemo(() => {
    const workspaceIds = new Set(searchedWorkspaces.map((workspace) => workspace.id));
    return workspaceSkills.filter((skill) => {
      if (internalOnly && skill.is_external) return false;
      const containerWorkspaceId = skill.added_to_workspace_id ?? skill.workspace_id;
      return workspaceIds.has(containerWorkspaceId);
    });
  }, [internalOnly, searchedWorkspaces, workspaceSkills]);

  const selectedProductSkill = useMemo(
    () =>
      searchedSkills.find(
        (skill) =>
          skill.id === selectedProductSkillId ||
          (selectedProductSkillSlug && skill.slug === selectedProductSkillSlug)
      ) ?? null,
    [searchedSkills, selectedProductSkillId, selectedProductSkillSlug]
  );

  useEffect(() => {
    if (!selectedProductSkillId) return;
    if (selectedProductSkill) return;
    setSelectedProductSkillId("");
  }, [selectedProductSkill, selectedProductSkillId]);

  useEffect(() => {
    if (!selectedProductSkillSlug || !selectedProductSkill || selectedProductSkillId) return;
    setSelectedProductSkillId(selectedProductSkill.id);
  }, [selectedProductSkill, selectedProductSkillId, selectedProductSkillSlug]);

  useEffect(() => {
    if (!selectedProductSkillId && !selectedProductSkillSlug) return;
    setSelectedFolderId("");
    setSelectedPageId("");
  }, [selectedProductSkillId, selectedProductSkillSlug]);

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
      const includeTables = contentScope === "all" || contentScope === "tables";
      const includeSkills = contentScope === "all" || contentScope === "skills";
      const workspace =
        workspaces.find((item) => item.id === selectedWorkspaceId) ??
        searchedWorkspaces[0] ??
        null;

      if (selectedSessionId && selectedWorkspaceId) {
        const events = await getSessionEvents(selectedWorkspaceId, selectedSessionId);
        if (workspace) {
          nextResults.push(...searchSingleSession(workspace, selectedSessionId, events, q));
        }
        setResults(sortResults(nextResults));
        return;
      }

      const selectedSkillSlug = selectedProductSkill?.slug ?? selectedProductSkillSlug;
      if (selectedSkillSlug) {
        const detail = await getPublicSkill(selectedSkillSlug);
        if (includeSkills) {
          nextResults.push(
            ...searchSkills([{ ...detail.skill, workspace_name: detail.workspace_name }], q)
          );
        }
        nextResults.push(
          ...searchPublicSkillItems(detail, q, {
            includePages,
            includeSessions,
            includeTables,
          })
        );
        setResults(sortResults(nextResults));
        return;
      }

      if (includeSkills && !selectedFolderId && !selectedPageId) {
        nextResults.push(...searchSkills(searchedSkills, q));
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
          ...searchPages(pageGroups, q, {
            selectedFolderId,
            selectedPageId,
            folderIds,
          })
        );
        if (pageGroups.length < searchedWorkspaces.length) {
          setError("Page search is unavailable for one or more workspaces.");
        }
      }

      if (includeTables && !selectedFolderId && !selectedPageId) {
        const workspaceIds = new Set(searchedWorkspaces.map((item) => item.id));
        const { tables } = await listAllTables();
        nextResults.push(
          ...searchTables(
            tables.filter((table) => {
              if (!table.workspace_id) return !selectedWorkspaceId;
              return workspaceIds.has(table.workspace_id);
            }),
            q
          )
        );
      }

      setResults(sortResults(nextResults));
      track("web.search_query", {
        scope: contentScope,
        has_results: nextResults.length > 0,
        result_count_bucket: bucketCount(nextResults.length),
      });
    } catch (err) {
      setError(err instanceof Error ? err.message : "Search failed");
      setResults([]);
    } finally {
      setSearching(false);
    }
  }, [
    contentScope,
    query,
    searchedSkills,
    searchedWorkspaces,
    selectedFolderId,
    selectedPageId,
    selectedProductSkill,
    selectedProductSkillSlug,
    selectedSessionId,
    selectedWorkspaceId,
    workspaces,
    sidebars,
  ]);

  useEffect(() => {
    if (!searchParams.get("q")) return;
    if (fetching) return;
    handleSearch();
  }, [fetching, handleSearch, searchParams]);

  if (loading) {
    return <BasicPageSkeleton />;
  }
  if (!user) return null;
  if (fetching) {
    return (
      <AppShell user={user} onLogout={logout}>
        <SearchSkeleton />
      </AppShell>
    );
  }

  return (
    <AppShell user={user} onLogout={logout}>
      <div className="mx-auto w-full max-w-[1180px] px-6 py-8">
        <header className="border-b border-border-subtle pb-6">
          <p className="font-mono text-[11px] font-medium uppercase tracking-[0.14em] text-muted">
            Search
          </p>
          <h1 className="mt-3 font-display text-[34px] font-bold tracking-tight text-foreground">
            Search pages, sessions, tables, and Skills.
          </h1>
          <p className="mt-2 max-w-[700px] text-[14.5px] leading-relaxed text-muted">
            Search one workspace, one Skill, a folder inside a workspace, or
            internal knowledge only. Skill results are published bundles created from
            workspace pages, tables, and sessions.
          </p>
        </header>

        <div className="mt-6 grid gap-5 lg:grid-cols-[280px_minmax(0,1fr)]">
          <aside className="rounded-lg border border-border bg-surface p-4">
            <div className="flex flex-col gap-4">
              <div className="flex flex-col gap-1.5">
                <span className="text-[12px] font-medium text-foreground">Workspace</span>
                <CustomSelect
                  value={selectedWorkspaceId}
                  options={[
                    { value: "", label: "All workspaces" },
                    ...workspaces.map((workspace) => ({
                      value: workspace.id,
                      label: workspace.name,
                    })),
                  ]}
                  onChange={(next) => {
                    setSelectedWorkspaceId(next);
                    setSelectedFolderId("");
                    setSelectedPageId("");
                    setSelectedProductSkillId("");
                    setSelectedProductSkillSlug("");
                    setSelectedSessionId("");
                  }}
                  ariaLabel="Workspace"
                  className="w-full rounded-md border border-border bg-base px-2 py-2 text-[13px] text-foreground focus:border-brand focus:outline-none"
                  menuClassName="text-[13px]"
                />
              </div>

              <div className="flex flex-col gap-1.5">
                <span className="text-[12px] font-medium text-foreground">Skill</span>
                <CustomSelect
                  value={selectedProductSkillId}
                  options={[
                    { value: "", label: "All Skills" },
                    ...searchedSkills.map((skill) => ({
                      value: skill.id,
                      label: skill.title + (skill.forked_from_skill_id ? " (Fork)" : ""),
                    })),
                  ]}
                  onChange={(next) => {
                    setSelectedProductSkillId(next);
                    setSelectedProductSkillSlug("");
                  }}
                  ariaLabel="Skill"
                  className="w-full rounded-md border border-border bg-base px-2 py-2 text-[13px] text-foreground focus:border-brand focus:outline-none"
                  menuClassName="text-[13px]"
                />
              </div>

              {selectedSessionId ? (
                <div className="flex flex-col gap-1.5">
                  <span className="text-[12px] font-medium text-foreground">Session</span>
                  <div className="truncate rounded-md border border-border bg-base px-2 py-2 font-mono text-[12px] text-foreground">
                    #{selectedSessionId}
                  </div>
                </div>
              ) : null}

              <div className="flex flex-col gap-1.5">
                <span className="text-[12px] font-medium text-foreground">Folder</span>
                <CustomSelect
                  value={selectedFolderId}
                  options={[
                    {
                      value: "",
                      label: selectedProductSkillId ? "Skill selected" : "Entire workspace",
                    },
                    ...folderOptions.map((folder) => ({
                      value: folder.id,
                      label: folder.name,
                    })),
                  ]}
                  onChange={(next) => {
                    setSelectedFolderId(next);
                    if (next) setSelectedPageId("");
                  }}
                  disabled={!selectedWorkspaceId || Boolean(selectedProductSkillId || selectedPageId)}
                  ariaLabel="Folder"
                  className="w-full rounded-md border border-border bg-base px-2 py-2 text-[13px] text-foreground focus:border-brand focus:outline-none"
                  menuClassName="text-[13px]"
                />
              </div>

              <div className="flex flex-col gap-1.5">
                <span className="text-[12px] font-medium text-foreground">Page</span>
                <CustomSelect
                  value={selectedPageId}
                  options={[
                    {
                      value: "",
                      label: selectedProductSkillId
                        ? "Skill selected"
                        : selectedFolderId
                          ? "Folder selected"
                          : "Any page",
                    },
                    ...pageOptions.map((page) => ({
                      value: page.id,
                      label: page.name,
                    })),
                  ]}
                  onChange={(next) => {
                    setSelectedPageId(next);
                    if (next) setSelectedFolderId("");
                  }}
                  disabled={!selectedWorkspaceId || Boolean(selectedProductSkillId || selectedFolderId)}
                  ariaLabel="Page"
                  className="w-full rounded-md border border-border bg-base px-2 py-2 text-[13px] text-foreground focus:border-brand focus:outline-none"
                  menuClassName="text-[13px]"
                />
              </div>

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
                placeholder="Search for a decision, transcript, table, Skill, or page..."
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

            {searching && <SearchResultsSkeleton />}

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
                    {results.length} ranked by relevance
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

function searchSingleSession(
  workspace: Pick<Workspace, "id" | "name">,
  sessionId: string,
  events: SessionEvent[],
  query: string
): SearchResult[] {
  const matches = events.filter((event) =>
    textIncludes(query, sessionId, event.agent_name, event.tool_name, event.content)
  );
  if (matches.length === 0) return [];

  const bestMatch = matches.reduce((best, event) => {
    const bestScore = scoreSessionEvent(query, sessionId, best);
    const eventScore = scoreSessionEvent(query, sessionId, event);
    if (eventScore !== bestScore) return eventScore > bestScore ? event : best;
    if (!best.created_at) return event;
    if (!event.created_at) return best;
    return new Date(event.created_at) > new Date(best.created_at) ? event : best;
  }, matches[0]);
  const latest = matches.reduce((best, event) => {
    if (!best.created_at) return event;
    if (!event.created_at) return best;
    return new Date(event.created_at) > new Date(best.created_at) ? event : best;
  }, matches[0]);

  return [
    {
      id: `${workspace.id}:${sessionId}`,
      kind: "Session",
      title: sessionId,
      href: `/sessions/${encodeURIComponent(sessionId)}`,
      sourceName: workspace.name,
      detail: sessionEventSnippet(bestMatch, query),
      updatedAt: latest.created_at ?? new Date().toISOString(),
      relevance: scoreSessionEvent(query, sessionId, bestMatch),
    },
  ];
}

function searchSkills(skills: SearchableSkill[], query: string): SearchResult[] {
  return skills
    .map((skill) => {
      const relevance = scoreValues(query, [
        { value: skill.title, weight: 8 },
        { value: skill.description, weight: 3 },
        { value: skill.workspace_name, weight: 1 },
      ]);
      return { skill, relevance };
    })
    .filter(({ relevance }) => relevance > 0)
    .map(({ skill, relevance }) => ({
      id: skill.id,
      kind: "Skill" as const,
      title: skill.title,
      href: `/skills/${skill.slug}`,
      sourceName: skill.workspace_name,
      detail:
        (skill.forked_from_skill_id ? "Forked Skill" : "Skill") +
        ` / ${skill.description || `${skill.items.length} items`}`,
      updatedAt: skill.updated_at,
      relevance,
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
      const relevance = scoreWorkspaceEvent(query, event);
      if (
        existing &&
        (existing.relevance > relevance ||
          (existing.relevance === relevance &&
            new Date(existing.updatedAt) >= new Date(event.created_at)))
      ) {
        continue;
      }
      resultsBySession.set(id, {
        id,
        kind: "Session",
        title: event.session_id,
        href: `/sessions/${encodeURIComponent(event.session_id)}`,
        sourceName: workspace.name,
        detail: sessionSearchSnippet(event, query),
        updatedAt: event.created_at,
        relevance,
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

function sessionEventSnippet(event: SessionEvent, query: string): string {
  const content = event.content.trim();
  if (!content) return `${event.agent_name || "agent"} session event`;

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
  query: string,
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
        href: `/p/${page.id}`,
        sourceName: workspace.name,
        detail:
          page.content_type === "html"
            ? stripHtml(page.content_html ?? "").slice(0, 220) || "HTML page"
            : page.content_markdown?.slice(0, 220) || "Markdown page",
        updatedAt: page.updated_at,
        relevance: scorePage(query, page),
      }))
  );
}

function searchTables(tables: TableWithWorkspace[], query: string): SearchResult[] {
  return tables
    .map((table) => {
      const relevance = scoreValues(query, [
        { value: table.name, weight: 8 },
        { value: table.description, weight: 3 },
        { value: table.columns.map((column) => column.name).join(" "), weight: 2 },
        { value: table.workspace_name ?? undefined, weight: 1 },
      ]);
      return { table, relevance };
    })
    .filter(({ relevance }) => relevance > 0)
    .map(({ table, relevance }) => ({
      id: table.id,
      kind: "Table" as const,
      title: table.name,
      href: tableSearchHref(table),
      sourceName: table.workspace_name ?? "Personal",
      detail: tableSearchDetail(table),
      updatedAt: table.updated_at,
      relevance,
    }));
}

function tableSearchHref(table: TableWithWorkspace): string {
  return `/tables/${table.id}`;
}

function tableSearchDetail(table: TableWithWorkspace): string {
  if (table.description.trim()) return table.description;
  const parts = [`${table.columns.length} column${table.columns.length === 1 ? "" : "s"}`];
  if (typeof table.row_count === "number") {
    parts.push(`${table.row_count} row${table.row_count === 1 ? "" : "s"}`);
  }
  return parts.join(" / ");
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

function searchPublicSkillItems(
  detail: PublicSkillDetail,
  query: string,
  scope: { includePages: boolean; includeSessions: boolean; includeTables: boolean }
): SearchResult[] {
  return detail.items.flatMap((item, index) => {
    if (item.object_type === "folder" && scope.includePages) {
      return searchPublicFolder(detail, item, index, query);
    }
    if (item.object_type === "page" && scope.includePages) {
      return searchPublicPage(detail, item, index, query);
    }
    if (item.object_type === "session" && scope.includeSessions) {
      return searchPublicSession(detail, item, index, query);
    }
    if (item.object_type === "table" && scope.includeTables) {
      return searchPublicTable(detail, item, index, query);
    }
    return [];
  });
}

function searchPublicFolder(
  detail: PublicSkillDetail,
  item: PublicSkillDetail["items"][number],
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
      href: `/skills/${detail.skill.slug}#item-${index}`,
      sourceName: detail.skill.title,
      detail: pageSnippet(page.content_markdown, page.content_html),
      updatedAt: page.updated_at || detail.skill.updated_at,
      relevance: scoreValues(query, [
        { value: page.name, weight: 8 },
        { value: page.content_markdown, weight: 2 },
        { value: stripHtml(page.content_html ?? ""), weight: 2 },
        { value: detail.skill.title, weight: 1 },
      ]),
    }));
}

function searchPublicPage(
  detail: PublicSkillDetail,
  item: PublicSkillDetail["items"][number],
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
      href: `/skills/${detail.skill.slug}#item-${index}`,
      sourceName: detail.skill.title,
      detail: pageSnippet(page.content_markdown, page.content_html),
      updatedAt: page.updated_at || detail.skill.updated_at,
      relevance: scoreValues(query, [
        { value: page.name, weight: 8 },
        { value: page.content_markdown, weight: 2 },
        { value: stripHtml(page.content_html ?? ""), weight: 2 },
        { value: detail.skill.title, weight: 1 },
      ]),
    },
  ];
}

function searchPublicSession(
  detail: PublicSkillDetail,
  item: PublicSkillDetail["items"][number],
  index: number,
  query: string
): SearchResult[] {
  const inline = item.inline as {
    session?: {
      id?: string;
      session_id: string;
      agent_name?: string | null;
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
  if (!textIncludes(query, session.session_id, session.agent_name, eventText)) {
    return [];
  }

  return [
    {
      id: session.id || item.object_id,
      kind: "Session" as const,
      title: sessionTitle(session),
      href: `/skills/${detail.skill.slug}#item-${index}`,
      sourceName: detail.skill.title,
      detail: sessionSnippet(session),
      updatedAt: session.finished_at || session.started_at || detail.skill.updated_at,
      relevance: scoreValues(query, [
        { value: session.session_id, weight: 5 },
        { value: session.agent_name, weight: 2 },
        { value: eventText, weight: 3 },
        { value: detail.skill.title, weight: 1 },
      ]),
    },
  ];
}

type PublicTableColumn = { name?: string | null };
type PublicTableRow = { data?: Record<string, unknown> | null };

function searchPublicTable(
  detail: PublicSkillDetail,
  item: PublicSkillDetail["items"][number],
  index: number,
  query: string
): SearchResult[] {
  const inline = item.inline as {
    description?: string | null;
    columns?: PublicTableColumn[];
    rows?: PublicTableRow[];
  };
  const columns = inline.columns ?? [];
  const rows = inline.rows ?? [];
  const columnText = columns.map((column) => column.name ?? "").join(" ");
  const rowsText = rows.map(tableRowText).join(" ");
  if (!textIncludes(query, item.label, inline.description, columnText, rowsText)) return [];

  return [
    {
      id: item.object_id,
      kind: "Table" as const,
      title: item.label,
      href: `/skills/${detail.skill.slug}#item-${index}`,
      sourceName: detail.skill.title,
      detail: publicTableSnippet(inline.description, columns, rows, query),
      updatedAt: detail.skill.updated_at,
      relevance: scoreValues(query, [
        { value: item.label, weight: 8 },
        { value: inline.description, weight: 3 },
        { value: columnText, weight: 2 },
        { value: rowsText, weight: 1 },
        { value: detail.skill.title, weight: 1 },
      ]),
    },
  ];
}

function publicTableSnippet(
  description: string | null | undefined,
  columns: PublicTableColumn[],
  rows: PublicTableRow[],
  query: string
): string {
  if (description?.trim()) return description.slice(0, 220);

  const matchingRow = rows.find((row) => textIncludes(query, tableRowText(row)));
  if (matchingRow) return tableRowText(matchingRow).slice(0, 220);

  return `${columns.length} column${columns.length === 1 ? "" : "s"}, ${rows.length} row${
    rows.length === 1 ? "" : "s"
  }`;
}

function tableRowText(row: PublicTableRow): string {
  return Object.values(row.data ?? {}).map(searchValueText).filter(Boolean).join(" ");
}

function searchValueText(value: unknown): string {
  if (value == null) return "";
  if (typeof value === "string") return value;
  if (typeof value === "number" || typeof value === "boolean") return String(value);
  if (Array.isArray(value)) return value.map(searchValueText).filter(Boolean).join(" ");
  if (typeof value === "object") {
    return Object.values(value as Record<string, unknown>)
      .map(searchValueText)
      .filter(Boolean)
      .join(" ");
  }
  return "";
}

function textIncludes(query: string, ...values: (string | null | undefined)[]): boolean {
  const text = normalizeSearchText(values.filter(Boolean).join(" "));
  const terms = searchTerms(query);
  if (!text || terms.length === 0) return false;

  const phrase = terms.join(" ");
  return text.includes(phrase) || terms.every((term) => text.includes(term));
}

function pageSnippet(markdown?: string | null, html?: string | null): string {
  if (markdown?.trim()) return markdown.slice(0, 220);
  if (html?.trim()) return stripHtml(html).slice(0, 220);
  return "Page in this skill";
}

function sessionSnippet(session: {
  agent_name?: string | null;
  events?: { event_type: string; tool_name?: string | null; content: string }[];
}): string {
  const firstEvent = session.events?.find((event) => event.content.trim());
  if (!firstEvent) return `${session.agent_name || "Agent"} session in this skill`;
  return firstEvent.content.slice(0, 220);
}

function sessionTitle(session: {
  session_id: string;
  events?: { content: string }[];
}): string {
  const firstEvent = session.events?.find((event) => event.content.trim());
  if (!firstEvent) return session.session_id;
  return firstEvent.content.split(/\r?\n/)[0]?.trim().slice(0, 80) || session.session_id;
}

function sortResults(results: SearchResult[]): SearchResult[] {
  return [...results].sort((a, b) => {
    if (b.relevance !== a.relevance) return b.relevance - a.relevance;
    return new Date(b.updatedAt).getTime() - new Date(a.updatedAt).getTime();
  });
}

function scoreSessionEvent(query: string, sessionId: string, event: SessionEvent): number {
  return scoreValues(query, [
    { value: sessionId, weight: 8 },
    { value: event.agent_name, weight: 3 },
    { value: event.tool_name, weight: 2 },
    { value: event.content, weight: 1 },
  ]);
}

function scoreWorkspaceEvent(query: string, event: WorkspaceHistoryEvent): number {
  const rank = typeof event.rank === "number" ? event.rank * 1000 : 0;
  return (
    rank +
    scoreValues(query, [
      { value: event.session_id, weight: 6 },
      { value: event.agent_name, weight: 3 },
      { value: event.tool_name, weight: 2 },
      { value: event.event_type, weight: 1 },
      { value: event.content, weight: 1 },
    ])
  );
}

function scorePage(query: string, page: Page): number {
  const rankedPage = page as Page & { rank?: number; similarity?: number };
  const rank = typeof rankedPage.rank === "number" ? rankedPage.rank * 1000 : 0;
  const similarity = typeof rankedPage.similarity === "number" ? rankedPage.similarity * 100 : 0;

  return (
    rank +
    similarity +
    scoreValues(query, [
      { value: page.name, weight: 8 },
      { value: page.content_markdown, weight: 2 },
      { value: stripHtml(page.content_html ?? ""), weight: 2 },
    ])
  );
}

function scoreValues(
  query: string,
  values: { value: string | null | undefined; weight: number }[]
): number {
  const terms = searchTerms(query);
  if (terms.length === 0) return 0;

  const phrase = terms.join(" ");
  let score = 0;
  for (const { value, weight } of values) {
    const text = normalizeSearchText(value ?? "");
    if (!text) continue;

    const words = new Set(text.split(" "));
    if (text === phrase) score += 100 * weight;
    if (text.startsWith(phrase)) score += 40 * weight;
    if (text.includes(phrase)) score += 30 * weight;
    if (terms.every((term) => text.includes(term))) score += 12 * weight;

    for (const term of terms) {
      if (words.has(term)) {
        score += 8 * weight;
      } else if (text.includes(term)) {
        score += 3 * weight;
      }
    }
  }
  return score;
}

function searchTerms(query: string): string[] {
  return normalizeSearchText(query).split(" ").filter(Boolean);
}

function normalizeSearchText(value: string): string {
  return value.toLowerCase().replace(/[^a-z0-9]+/g, " ").trim();
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
