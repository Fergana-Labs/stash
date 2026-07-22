"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { Suspense, useCallback, useEffect, useMemo, useState, type ReactNode } from "react";
import CustomSelect from "../../../components/CustomSelect";
import { BasicPageSkeleton, SearchResultsSkeleton, SearchSkeleton } from "../../../components/SkeletonStates";
import { useAuth } from "../../../hooks/useAuth";
import { track } from "../../../lib/analytics";
import {
  getSidebar,
  getPublicSkill,
  getSessionEvents,
  listAllTables,
  listSkills,
  searchEvents,
  searchPages as searchPagesApi,
  type HistoryEvent,
  type PublicSkillDetail,
  type SessionEvent,
  type Sidebar,
  type Skill,
  type TreeFolder,
} from "../../../lib/api";
import type { Page, TableWithOwner } from "../../../lib/types";
import { skillItemPath } from "../../../lib/localSkill";
import { routes } from "../../../lib/workspace-routes";

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
  detail: ReactNode;
  updatedAt: string;
  relevance: number;
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
  const searchParams = useSearchParams();
  const { user, loading } = useAuth();
  const initialSessionId = searchParams.get("session") ?? "";
  const [skills, setSkills] = useState<Skill[]>([]);
  const [sidebar, setSidebar] = useState<Sidebar | null>(null);
  const [selectedProductSkillId, setSelectedProductSkillId] = useState("");
  const [selectedProductSkillSlug, setSelectedProductSkillSlug] = useState(
    searchParams.get("skill") ?? ""
  );
  const [selectedFolderId, setSelectedFolderId] = useState(searchParams.get("folder") ?? "");
  const [selectedPageId, setSelectedPageId] = useState(searchParams.get("page") ?? "");
  const [selectedSessionId] = useState(initialSessionId);
  const [contentScope, setContentScope] = useState<ContentScope>(
    () => initialContentScope(searchParams.get("content"), initialSessionId)
  );
  const [results, setResults] = useState<SearchResult[]>([]);
  const [searchedQuery, setSearchedQuery] = useState("");
  const [fetching, setFetching] = useState(true);
  const [searching, setSearching] = useState(false);
  const [error, setError] = useState("");

  const loadData = useCallback(async () => {
    setFetching(true);
    setError("");
    try {
      const [skillList, sidebarData] = await Promise.all([listSkills(), getSidebar()]);
      setSkills(skillList);
      setSidebar(sidebarData);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load search data");
    } finally {
      setFetching(false);
    }
  }, []);

  useEffect(() => {
    if (user) loadData();
  }, [user, loadData]);

  // Skill-scoped item search reads through the public-skill payload, so the
  // picker only offers published skills (the ones with a slug).
  const publishedSkills = useMemo(
    () => skills.filter((skill) => skill.published !== null),
    [skills]
  );

  const selectedProductSkill = useMemo(
    () =>
      publishedSkills.find(
        (skill) =>
          skill.published!.id === selectedProductSkillId ||
          (selectedProductSkillSlug && skill.published!.slug === selectedProductSkillSlug)
      ) ?? null,
    [publishedSkills, selectedProductSkillId, selectedProductSkillSlug]
  );

  useEffect(() => {
    if (!selectedProductSkillId) return;
    if (selectedProductSkill) return;
    setSelectedProductSkillId("");
  }, [selectedProductSkill, selectedProductSkillId]);

  useEffect(() => {
    if (!selectedProductSkillSlug || !selectedProductSkill || selectedProductSkillId) return;
    setSelectedProductSkillId(selectedProductSkill.published!.id);
  }, [selectedProductSkill, selectedProductSkillId, selectedProductSkillSlug]);

  useEffect(() => {
    if (!selectedProductSkillId && !selectedProductSkillSlug) return;
    setSelectedFolderId("");
    setSelectedPageId("");
  }, [selectedProductSkillId, selectedProductSkillSlug]);

  const folderOptions = useMemo(() => sidebar?.files.folders ?? [], [sidebar]);
  const pageOptions = useMemo(() => sidebar?.files.pages ?? [], [sidebar]);

  const sourceName = user?.display_name ?? "You";

  const handleSearch = useCallback(async (rawQuery: string) => {
    const q = rawQuery.trim();
    if (!q) {
      setResults([]);
      setSearchedQuery("");
      setSearching(false);
      return;
    }

    setSearching(true);
    setError("");
    setSearchedQuery(q);
    try {
      const nextResults: SearchResult[] = [];
      const includeSessions = contentScope === "all" || contentScope === "sessions";
      const includePages = contentScope === "all" || contentScope === "pages";
      const includeTables = contentScope === "all" || contentScope === "tables";
      const includeSkills = contentScope === "all" || contentScope === "skills";

      if (selectedSessionId) {
        const events = await getSessionEvents(selectedSessionId);
        nextResults.push(...searchSingleSession(sourceName, selectedSessionId, events, q));
        setResults(sortResults(nextResults));
        return;
      }

      const selectedSkillSlug =
        selectedProductSkill?.published?.slug ?? selectedProductSkillSlug;
      if (selectedSkillSlug) {
        const detail = await getPublicSkill(selectedSkillSlug);
        if (includeSkills) {
          nextResults.push(...searchPublicSkillRecord(detail, q));
        }
        nextResults.push(
          ...searchPublicSkillItems(detail, q, { includePages, includeTables })
        );
        setResults(sortResults(nextResults));
        return;
      }

      if (includeSkills && !selectedFolderId && !selectedPageId) {
        nextResults.push(...searchSkills(skills, q, sourceName));
      }

      if (includeSessions && !selectedFolderId && !selectedPageId) {
        const events = await searchEvents(q, 100);
        nextResults.push(...searchSessionsFromEvents(events, q, sourceName));
      }

      if (includePages) {
        const pages = await searchPagesApi(q, 50);
        const folderIds = sidebar
          ? descendantFolderIds(sidebar.files.folders, selectedFolderId)
          : new Set<string>();
        nextResults.push(
          ...searchPages(pages, q, sourceName, {
            selectedFolderId,
            selectedPageId,
            folderIds,
          })
        );
      }

      if (includeTables && !selectedFolderId && !selectedPageId) {
        const { tables } = await listAllTables();
        nextResults.push(...searchTables(tables, q));
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
    skills,
    selectedFolderId,
    selectedPageId,
    selectedProductSkill,
    selectedProductSkillSlug,
    selectedSessionId,
    sidebar,
    sourceName,
  ]);

  // The header search input writes the query into the URL; re-run the search
  // in real time as it (or any filter) changes.
  const urlQuery = searchParams.get("q") ?? "";

  useEffect(() => {
    if (fetching) return;
    handleSearch(urlQuery);
  }, [fetching, handleSearch, urlQuery]);

  if (loading) {
    return <BasicPageSkeleton />;
  }
  if (!user) return null;
  if (fetching) {
    return <SearchSkeleton />;
  }

  return (
    <WorkspaceShell user={user} onLogout={logout}>
      <div className="mx-auto w-full max-w-[1180px] px-6 py-8">
        <div className="flex flex-col gap-5">
          <div className="flex flex-wrap items-center gap-2">
            {selectedSessionId ? (
              <span className="inline-flex h-7 items-center gap-1.5 rounded-full border border-border bg-surface px-3 font-mono text-xs text-foreground">
                #{selectedSessionId}
              </span>
            ) : null}

            <CustomSelect
              value={selectedFolderId}
              options={[
                { value: "", label: "All folders" },
                ...folderOptions.map((folder) => ({ value: folder.id, label: folder.name })),
              ]}
              onChange={(next) => {
                setSelectedFolderId(next);
                if (next) setSelectedPageId("");
              }}
              disabled={Boolean(selectedPageId)}
              ariaLabel="Folder"
              searchable
              searchPlaceholder="Filter folders…"
              className="flex h-7 items-center gap-1.5 rounded-full border border-border bg-surface px-3 text-[12.5px] text-foreground transition-colors duration-150 ease-out hover:border-[var(--color-brand-300)]"
              menuClassName="text-[12.5px]"
            />

            <CustomSelect
              value={selectedPageId}
              options={[
                { value: "", label: "Any page" },
                ...pageOptions.map((page) => ({ value: page.id, label: page.name })),
              ]}
              onChange={(next) => {
                setSelectedPageId(next);
                if (next) setSelectedFolderId("");
              }}
              disabled={Boolean(selectedFolderId)}
              ariaLabel="Page"
              searchable
              searchPlaceholder="Filter pages…"
              className="flex h-7 items-center gap-1.5 rounded-full border border-border bg-surface px-3 text-[12.5px] text-foreground transition-colors duration-150 ease-out hover:border-[var(--color-brand-300)]"
              menuClassName="text-[12.5px]"
            />

            <CustomSelect
              value={contentScope}
              options={CONTENT_SCOPES.map((scope) => ({
                value: scope.id,
                label: scope.id === "all" ? "All types" : scope.label,
              }))}
              onChange={(next) => setContentScope(next as ContentScope)}
              ariaLabel="Content"
              searchable
              searchPlaceholder="Filter types…"
              className="flex h-7 items-center gap-1.5 rounded-full border border-border bg-surface px-3 text-[12.5px] text-foreground transition-colors duration-150 ease-out hover:border-[var(--color-brand-300)]"
              menuClassName="text-[12.5px]"
            />
          </div>

          <main className="min-w-0">
            {error && (
              <div className="mt-4 rounded-md border border-red-300 bg-red-50 px-3 py-2 text-[13px] text-red-700">
                {error}
              </div>
            )}

            {searching && <SearchResultsSkeleton />}

            {!searching && searchedQuery && results.length === 0 && !error && (
              <p className="py-10 text-center text-[13px] text-muted-foreground">
                No results found for &ldquo;{searchedQuery}&rdquo;.
              </p>
            )}

            {!searching && results.length > 0 && (
              <section className="mt-5">
                <div className="mb-3 flex items-center justify-between gap-3">
                  <h2 className="font-display text-lg font-semibold text-foreground">
                    Results
                  </h2>
                  <p className="font-mono text-[11px] uppercase tracking-[0.12em] text-muted-foreground">
                    {results.length} ranked by relevance
                  </p>
                </div>
                <div className="flex flex-col gap-2">
                  {results.map((result) => (
                    <Link
                      key={`${result.kind}:${result.id}`}
                      href={result.href}
                      className="rounded-lg border border-border bg-base px-4 py-3 transition-colors duration-150 ease-out hover:border-[var(--color-brand-300)] hover:bg-[var(--color-brand-50)]"
                    >
                      <div className="flex items-start justify-between gap-3">
                        <div className="min-w-0">
                          <div className="flex items-center gap-2">
                            <span className="rounded-md border border-border-subtle px-1.5 py-0.5 text-[10px] uppercase tracking-wide text-muted-foreground">
                              {result.kind}
                            </span>
                            <h3 className="truncate text-[14px] font-semibold text-foreground">
                              {result.title}
                            </h3>
                          </div>
                          <p className="mt-1 line-clamp-2 text-[13px] leading-relaxed text-muted-foreground">
                            {result.detail}
                          </p>
                        </div>
                        <div className="shrink-0 text-right text-[11px] text-muted-foreground">
                          <div>{result.sourceName}</div>
                          <div>{relativeTime(result.updatedAt)}</div>
    <div className="mx-auto w-full max-w-[1180px] px-6 py-8">
      <div className="flex flex-col gap-5">
        <div className="flex flex-wrap items-center gap-2">
          {selectedSessionId ? (
            <span className="inline-flex h-7 items-center gap-1.5 rounded-full border border-border bg-surface px-3 font-mono text-[12px] text-foreground">
              #{selectedSessionId}
            </span>
          ) : null}

          <CustomSelect
            value={selectedFolderId}
            options={[
              { value: "", label: "All folders" },
              ...folderOptions.map((folder) => ({ value: folder.id, label: folder.name })),
            ]}
            onChange={(next) => {
              setSelectedFolderId(next);
              if (next) setSelectedPageId("");
            }}
            disabled={Boolean(selectedPageId)}
            ariaLabel="Folder"
            searchable
            searchPlaceholder="Filter folders…"
            className="flex h-7 items-center gap-1.5 rounded-full border border-border bg-surface px-3 text-[12.5px] text-foreground hover:border-[var(--color-brand-300)]"
            menuClassName="text-[12.5px]"
          />

          <CustomSelect
            value={selectedPageId}
            options={[
              { value: "", label: "Any page" },
              ...pageOptions.map((page) => ({ value: page.id, label: page.name })),
            ]}
            onChange={(next) => {
              setSelectedPageId(next);
              if (next) setSelectedFolderId("");
            }}
            disabled={Boolean(selectedFolderId)}
            ariaLabel="Page"
            searchable
            searchPlaceholder="Filter pages…"
            className="flex h-7 items-center gap-1.5 rounded-full border border-border bg-surface px-3 text-[12.5px] text-foreground hover:border-[var(--color-brand-300)]"
            menuClassName="text-[12.5px]"
          />

          <CustomSelect
            value={contentScope}
            options={CONTENT_SCOPES.map((scope) => ({
              value: scope.id,
              label: scope.id === "all" ? "All types" : scope.label,
            }))}
            onChange={(next) => setContentScope(next as ContentScope)}
            ariaLabel="Content"
            searchable
            searchPlaceholder="Filter types…"
            className="flex h-7 items-center gap-1.5 rounded-full border border-border bg-surface px-3 text-[12.5px] text-foreground hover:border-[var(--color-brand-300)]"
            menuClassName="text-[12.5px]"
          />
        </div>

        <main className="min-w-0">
          {error && (
            <div className="mt-4 rounded-md border border-red-300 bg-red-50 px-3 py-2 text-[13px] text-red-700">
              {error}
            </div>
          )}

          {searching && <SearchResultsSkeleton />}

          {!searching && searchedQuery && results.length === 0 && !error && (
            <p className="py-10 text-center text-[13px] text-muted-foreground">
              No results found for &ldquo;{searchedQuery}&rdquo;.
            </p>
          )}

          {!searching && results.length > 0 && (
            <section className="mt-5">
              <div className="mb-3 flex items-center justify-between gap-3">
                <h2 className="font-display text-[18px] font-semibold text-foreground">
                  Results
                </h2>
                <p className="font-mono text-[11px] uppercase tracking-[0.12em] text-muted-foreground">
                  {results.length} ranked by relevance
                </p>
              </div>
              <div className="flex flex-col gap-2">
                {results.map((result) => (
                  <Link
                    key={`${result.kind}:${result.id}`}
                    href={result.href}
                    className="rounded-lg border border-border bg-base px-4 py-3 transition-colors hover:border-[var(--color-brand-300)] hover:bg-[var(--color-brand-50)]"
                  >
                    <div className="flex items-start justify-between gap-3">
                      <div className="min-w-0">
                        <div className="flex items-center gap-2">
                          <span className="rounded-md border border-border-subtle px-1.5 py-0.5 text-[10px] uppercase tracking-wide text-muted-foreground">
                            {result.kind}
                          </span>
                          <h3 className="truncate text-[14px] font-semibold text-foreground">
                            {result.title}
                          </h3>
                        </div>
                        <p className="mt-1 line-clamp-2 text-[13px] leading-relaxed text-muted-foreground">
                          {result.detail}
                        </p>
                      </div>
                      <div className="flex-shrink-0 text-right text-[11px] text-muted-foreground">
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
  );
}

function searchSingleSession(
  sourceName: string,
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
      id: sessionId,
      kind: "Session",
      title: sessionId,
      href: routes.session(sessionId),

      sourceName,
      detail: contextSnippet(bestMatch.content, query) ?? sessionEventSnippet(bestMatch, query),
      updatedAt: latest.created_at ?? new Date().toISOString(),
      relevance: scoreSessionEvent(query, sessionId, bestMatch),
    },
  ];
}

function searchSkills(skills: Skill[], query: string, sourceName: string): SearchResult[] {
  return skills
    .map((skill) => {
      const relevance = scoreValues(query, [
        { value: skill.name, weight: 8 },
        { value: skill.description, weight: 3 },
      ]);
      return { skill, relevance };
    })
    .filter(({ relevance }) => relevance > 0)
    .map(({ skill, relevance }) => ({
      id: skill.folder_id,
      kind: "Skill" as const,
      title: skill.name,

      href: `/skills/folder/${skill.folder_id}`,
      sourceName,
      detail:
        contextSnippet(skill.description, query) ??
        `Skill / ${skill.description || `${skill.file_count} files`}`,
      updatedAt: skill.updated_at,
      relevance,
    }));
}

// The published skill record itself, scored as a result when a skill is the
// selected search scope.
function searchPublicSkillRecord(detail: PublicSkillDetail, query: string): SearchResult[] {
  const relevance = scoreValues(query, [
    { value: detail.skill.title, weight: 8 },
    { value: detail.skill.description, weight: 3 },
  ]);
  if (relevance <= 0) return [];
  return [
    {
      id: detail.skill.id,
      kind: "Skill" as const,
      title: detail.skill.title,
      href: `/skills/${detail.skill.slug}`,
      sourceName: detail.skill.owner_display_name ?? detail.skill.owner_name,
      detail:
        contextSnippet(detail.skill.description, query) ??
        `Skill / ${detail.skill.description || `${detail.contents.pages.length} pages`}`,
      updatedAt: detail.skill.updated_at,
      relevance,
    },
  ];
}

function searchSessionsFromEvents(
  events: HistoryEvent[],
  query: string,
  sourceName: string
): SearchResult[] {
  const resultsBySession = new Map<string, SearchResult>();
  for (const event of events) {
    if (!event.session_id) continue;
    const id = event.session_id;
    const existing = resultsBySession.get(id);
    const relevance = scoreHistoryEvent(query, event);
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
      href: routes.session(event.session_id),
      sourceName,
      detail: contextSnippet(event.content, query) ?? sessionSearchSnippet(event, query),
      updatedAt: event.created_at,
      relevance,
    });
  }
  return [...resultsBySession.values()];
}

function sessionSearchSnippet(event: HistoryEvent, query: string): string {
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
  pages: Page[],
  query: string,
  sourceName: string,
  scope: {
    selectedFolderId: string;
    selectedPageId: string;
    folderIds: Set<string>;
  }
): SearchResult[] {
  return pages
    .filter((page) => {
      if (scope.selectedPageId) return page.id === scope.selectedPageId;
      if (!scope.selectedFolderId) return true;
      return Boolean(page.folder_id && scope.folderIds.has(page.folder_id));
    })
    .map((page) => ({
      id: page.id,
      kind: "Page" as const,
      title: page.name,
      href: routes.page(page.id),
      sourceName,
      detail:
          contextSnippet(
            page.content_type === "html"
              ? stripHtml(page.content_html ?? "")
              : page.content_markdown ?? "",
            query
          ) ??
          (page.content_type === "html"
            ? stripHtml(page.content_html ?? "").slice(0, 220) || "HTML page"
            : page.content_markdown?.slice(0, 220) || "Markdown page"),
      updatedAt: page.updated_at,
      relevance: scorePage(query, page),
    }));
}

function searchTables(tables: TableWithOwner[], query: string): SearchResult[] {
  return tables
    .map((table) => {
      const relevance = scoreValues(query, [
        { value: table.name, weight: 8 },
        { value: table.description, weight: 3 },
        { value: table.columns.map((column) => column.name).join(" "), weight: 2 },
      ]);
      return { table, relevance };
    })
    .filter(({ relevance }) => relevance > 0)
    .map(({ table, relevance }) => ({
      id: table.id,
      kind: "Table" as const,
      title: table.name,
      href: routes.table(table.id),
      sourceName: table.owner_display_name ?? "Personal",
      detail:
        contextSnippet(
          [table.description, table.columns.map((column) => column.name).join(" ")]
            .filter(Boolean)
            .join(" "),
          query
        ) ?? tableSearchDetail(table),
      updatedAt: table.updated_at,
      relevance,
    }));
}

function tableSearchDetail(table: TableWithOwner): string {
  if (table.description.trim()) return table.description;
  const parts = [`${table.columns.length} column${table.columns.length === 1 ? "" : "s"}`];
  if (typeof table.row_count === "number") {
    parts.push(`${table.row_count} row${table.row_count === 1 ? "" : "s"}`);
  }
  return parts.join(" / ");
}

function descendantFolderIds(
  folders: TreeFolder[],
  selectedFolderId: string
): Set<string> {
  if (!selectedFolderId) return new Set();

  const childrenByParent = new Map<string, TreeFolder[]>();
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
  scope: { includePages: boolean; includeTables: boolean }
): SearchResult[] {
  const results: SearchResult[] = [];
  const slug = detail.skill.slug;

  if (scope.includePages) {
    for (const page of detail.contents.pages) {
      if (!textIncludes(query, page.name, page.content_markdown, page.content_html)) continue;
      results.push({
        id: page.id,
        kind: "Page",
        title: page.name,
        href: skillItemPath("page", page.id, slug),
        sourceName: detail.skill.title,
        detail:
          contextSnippet(
            page.content_markdown?.trim()
              ? page.content_markdown
              : stripHtml(page.content_html ?? ""),
            query
          ) ?? pageSnippet(page.content_markdown, page.content_html),
        updatedAt: page.updated_at || detail.skill.updated_at,
        relevance: scoreValues(query, [
          { value: page.name, weight: 8 },
          { value: page.content_markdown, weight: 2 },
          { value: stripHtml(page.content_html ?? ""), weight: 2 },
          { value: detail.skill.title, weight: 1 },
        ]),
      });
    }
  }

  if (scope.includeTables) {
    for (const table of detail.contents.tables) {
      const columnText = table.columns.map((column) => column.name ?? "").join(" ");
      const rowsText = table.rows.map(tableRowText).join(" ");
      if (!textIncludes(query, table.name, table.description, columnText, rowsText)) continue;
      results.push({
        id: table.id,
        kind: "Table",
        title: table.name,
        href: skillItemPath("table", table.id, slug),
        sourceName: detail.skill.title,
        detail:
          contextSnippet(
            [
              table.description,
              table.columns.map((column) => column.name ?? "").join(" "),
              table.rows.map(tableRowText).join(" "),
            ]
              .filter(Boolean)
              .join(" "),
            query
          ) ?? publicTableSnippet(table.description, table.columns, table.rows, query),
        updatedAt: detail.skill.updated_at,
        relevance: scoreValues(query, [
          { value: table.name, weight: 8 },
          { value: table.description, weight: 3 },
          { value: columnText, weight: 2 },
          { value: rowsText, weight: 1 },
          { value: detail.skill.title, weight: 1 },
        ]),
      });
    }
  }

  return results;
}

type PublicTableColumn = { name?: string | null };
type PublicTableRow = { data?: Record<string, unknown> | null };

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

function scoreHistoryEvent(query: string, event: HistoryEvent): number {
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

// Wraps every occurrence of the query in a <mark>, case-insensitively.
function highlightAll(text: string, query: string): ReactNode {
  const lower = text.toLowerCase();
  const needle = query.toLowerCase();
  const nodes: ReactNode[] = [];
  let cursor = 0;
  let key = 0;
  while (true) {
    const index = lower.indexOf(needle, cursor);
    if (index === -1) {
      nodes.push(text.slice(cursor));
      break;
    }
    if (index > cursor) nodes.push(text.slice(cursor, index));
    nodes.push(
      <mark key={key++} className="rounded-[3px] bg-[#fde68a] px-0.5 text-foreground">
        {text.slice(index, index + query.length)}
      </mark>
    );
    cursor = index + query.length;
  }
  return nodes;
}

// Context window around the FIRST occurrence of the query, with every match in
// that window highlighted. Returns null when the query is not present so
// callers can fall back to their default detail string.
function contextSnippet(
  source: string | null | undefined,
  query: string
): ReactNode | null {
  const text = (source ?? "").replace(/\s+/g, " ").trim();
  const trimmed = query.trim();
  if (!text || !trimmed) return null;

  const index = text.toLowerCase().indexOf(trimmed.toLowerCase());
  if (index === -1) return null;

  const start = Math.max(0, index - 80);
  const end = Math.min(text.length, index + trimmed.length + 140);
  return (
    <>
      {start > 0 ? "\u2026" : ""}
      {highlightAll(text.slice(start, end), trimmed)}
      {end < text.length ? "\u2026" : ""}
    </>
  );
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
