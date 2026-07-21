"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useCallback, useEffect, useMemo, useState, type ReactNode } from "react";
import WorkspaceShell from "@/components/workspace/workspace-shell";
import CustomSelect from "../../components/CustomSelect";
import SearchSourceFilter from "../../components/SearchSourceFilter";
import { providerForSourceType } from "../../components/integrations/connectors";
import { CLIENT_SIDE_TOKENS, unifiedSearchTokens } from "./unified-tokens";
import { BasicPageSkeleton, SearchResultsSkeleton, SearchSkeleton } from "../../components/SkeletonStates";
import { useAuth } from "../../hooks/useAuth";
import { track } from "../../lib/analytics";
import SourceDocViewer from "../../components/SourceDocViewer";
import {
  getSidebar,
  getPublicSkill,
  getSessionEvents,
  listAllTables,
  listSkills,
  listSources,
  searchSource,
  type PublicSkillDetail,
  type SessionEvent,
  type Sidebar,
  type SidebarSession,
  type Skill,
  type SourceSearchHit,
  type TreeFolder,
  type TreePage,
} from "../../lib/api";
import type { TableWithOwner } from "../../lib/types";

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
  kind: "Session" | "Page" | "Table" | "Skill" | "Source";
  title: string;
  // Connected-source hits have no internal route: they render as a row that
  // expands an inline document viewer instead of a link.
  href: string | null;
  external?: { source: string; ref: string; name?: string };
  sourceName: string;
  detail: ReactNode;
  // Unified search hits don't carry timestamps; rows without one hide the time.
  updatedAt: string | null;
  relevance: number;
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
  const [skills, setSkills] = useState<Skill[]>([]);
  const [sidebar, setSidebar] = useState<Sidebar | null>(null);
  const [selectedProductSkillId, setSelectedProductSkillId] = useState("");
  const [selectedProductSkillSlug, setSelectedProductSkillSlug] = useState(
    searchParams.get("skill") ?? ""
  );
  const [selectedFolderId, setSelectedFolderId] = useState(searchParams.get("folder") ?? "");
  const [selectedPageId, setSelectedPageId] = useState(searchParams.get("page") ?? "");
  const [selectedSessionId] = useState(initialSessionId);
  const [connectedProviders, setConnectedProviders] = useState<string[]>([]);
  // The chip stores what's UNCHECKED, so "all selected" is the default even
  // before the connected providers load, and the default sends no filter.
  const [deselectedSources, setDeselectedSources] = useState<Set<string>>(new Set());
  const [results, setResults] = useState<SearchResult[]>([]);
  const [sourceNotices, setSourceNotices] = useState<string[]>([]);
  const [hasMore, setHasMore] = useState(false);
  const [openExternalId, setOpenExternalId] = useState<string | null>(null);
  const [searchedQuery, setSearchedQuery] = useState("");
  const [fetching, setFetching] = useState(true);
  const [searching, setSearching] = useState(false);
  const [error, setError] = useState("");

  const loadData = useCallback(async () => {
    setFetching(true);
    setError("");
    try {
      const [skillList, sidebarData, sources] = await Promise.all([
        listSkills(),
        getSidebar(),
        listSources(),
      ]);
      setSkills(skillList);
      setSidebar(sidebarData);
      setConnectedProviders([...new Set(sources.map((s) => providerForSourceType[s.type]))]);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load search data");
    } finally {
      setFetching(false);
    }
  }, []);

  useEffect(() => {
    if (user) loadData();
  }, [user, loadData]);

  useEffect(() => {
    if (!loading && !user) router.push("/login");
  }, [user, loading, router]);

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

  const allSourceTokens = useMemo(
    () => ["files", "sessions", "skills", "tables", ...connectedProviders],
    [connectedProviders]
  );

  const handleSearch = useCallback(async (rawQuery: string) => {
    const q = rawQuery.trim();
    if (!q) {
      setResults([]);
      setSourceNotices([]);
      setHasMore(false);
      setSearchedQuery("");
      setSearching(false);
      return;
    }

    setSearching(true);
    setError("");
    setSourceNotices([]);
    setHasMore(false);
    setOpenExternalId(null);
    setSearchedQuery(q);
    try {
      const nextResults: SearchResult[] = [];
      const selected = allSourceTokens.filter((t) => !deselectedSources.has(t));
      const includePages = selected.includes("files");
      const includeTables = selected.includes("tables");
      const includeSkills = selected.includes("skills");

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

      // One unified call covers sessions + pages + connected sources, merged
      // and ranked server-side, narrowed to the sources chip's selection.
      // All-selected sends no filter — the server's default already searches
      // everything.
      const tokens = unifiedSearchTokens(
        { filtered: Boolean(selectedFolderId || selectedPageId) },
        selected
      );
      if (tokens !== null) {
        const allApiTokenCount = allSourceTokens.length - CLIENT_SIDE_TOKENS.length;
        const { results: hits, has_more } = await searchSource(q, {
          includeSources: tokens.length === allApiTokenCount ? undefined : tokens,
          limit: 50,
        });
        const folderIds = sidebar
          ? descendantFolderIds(sidebar.files.folders, selectedFolderId)
          : new Set<string>();
        nextResults.push(
          ...unifiedResults(hits, q, {
            sourceName,
            sessionsById: new Map((sidebar?.sessions ?? []).map((s) => [s.session_id, s])),
            pagesById: new Map((sidebar?.files.pages ?? []).map((p) => [p.id, p])),
            selectedFolderId,
            selectedPageId,
            folderIds,
          })
        );
        setSourceNotices(markerNotices(hits));
        setHasMore(has_more);
      }

      if (includeTables && !selectedFolderId && !selectedPageId) {
        const { tables } = await listAllTables();
        nextResults.push(...searchTables(tables, q));
      }

      setResults(sortResults(nextResults));
      track("web.search_query", {
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
    allSourceTokens,
    deselectedSources,
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
    return (
      <WorkspaceShell user={user} onLogout={logout}>
        <SearchSkeleton />
      </WorkspaceShell>
    );
  }

  return (
    <WorkspaceShell user={user} onLogout={logout}>
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

            <SearchSourceFilter
              tokens={allSourceTokens}
              deselected={deselectedSources}
              onToggle={(token) =>
                setDeselectedSources((prev) => {
                  const next = new Set(prev);
                  if (next.has(token)) next.delete(token);
                  else next.add(token);
                  return next;
                })
              }
            />
          </div>

          <main className="min-w-0">
            {error && (
              <div className="mt-4 rounded-md border border-red-300 bg-red-50 px-3 py-2 text-[13px] text-red-700">
                {error}
              </div>
            )}

            {searching && <SearchResultsSkeleton />}

            {!searching && sourceNotices.length > 0 && (
              <div className="mt-4 flex flex-col gap-1">
                {sourceNotices.map((notice) => (
                  <p key={notice} className="text-[12px] text-muted-foreground">
                    ⚠ {notice}
                  </p>
                ))}
              </div>
            )}

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
                  {results.map((result) => {
                    const key = `${result.kind}:${result.id}`;
                    if (result.external) {
                      return (
                        <div key={key}>
                          <button
                            type="button"
                            onClick={() =>
                              setOpenExternalId(openExternalId === key ? null : key)
                            }
                            className="w-full cursor-pointer rounded-lg border border-border bg-base px-4 py-3 text-left transition hover:border-[var(--color-brand-300)] hover:bg-[var(--color-brand-50)]"
                          >
                            <ResultCard result={result} />
                          </button>
                          {openExternalId === key && (
                            <SourceDocViewer
                              source={result.external.source}
                              providerLabel={result.sourceName}
                              refValue={result.external.ref}
                              name={result.external.name}
                              onClose={() => setOpenExternalId(null)}
                            />
                          )}
                        </div>
                      );
                    }
                    return (
                      <Link
                        key={key}
                        href={result.href!}
                        className="rounded-lg border border-border bg-base px-4 py-3 transition hover:border-[var(--color-brand-300)] hover:bg-[var(--color-brand-50)]"
                      >
                        <ResultCard result={result} />
                      </Link>
                    );
                  })}
                </div>
                {hasMore && (
                  <p className="mt-3 text-center text-[12px] text-muted-foreground">
                    Showing the top matches — refine your query to see more.
                  </p>
                )}
              </section>
            )}
          </main>
        </div>
      </div>
    </WorkspaceShell>
  );
}

function ResultCard({ result }: { result: SearchResult }) {
  return (
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
        {result.updatedAt && <div>{relativeTime(result.updatedAt)}</div>}
      </div>
    </div>
  );
}

function unifiedResults(
  hits: SourceSearchHit[],
  query: string,
  ctx: {
    sourceName: string;
    sessionsById: Map<string, SidebarSession>;
    pagesById: Map<string, TreePage>;
    selectedFolderId: string;
    selectedPageId: string;
    folderIds: Set<string>;
  }
): SearchResult[] {
  const results: SearchResult[] = [];
  const seenSessions = new Set<string>();
  for (const hit of hits) {
    if (!hit.ref) continue; // markers surface as notices, not result rows
    const snippet = hit.snippet ?? "";
    // Server rank carries the cross-source ordering; the client term score
    // keeps unified hits comparable with client-scored tables and skills.
    // Provider-id matches are lookups, not relevance guesses — always on top.
    const relevance = hit.exact_ref
      ? Number.POSITIVE_INFINITY
      : (hit.rank ?? 0) * 1000 +
        scoreValues(query, [
          { value: hit.name, weight: 8 },
          { value: snippet, weight: 1 },
        ]);

    if (hit.source === "sessions") {
      // Several matching events can point at the same session; hits arrive
      // rank-descending, so the first one is that session's best.
      if (seenSessions.has(hit.ref)) continue;
      seenSessions.add(hit.ref);
      const session = ctx.sessionsById.get(hit.ref);
      results.push({
        id: hit.ref,
        kind: "Session",
        title: session?.title || hit.ref,
        href: `/sessions/${encodeURIComponent(hit.ref)}`,
        sourceName: ctx.sourceName,
        detail: contextSnippet(snippet, query) ?? "",
        updatedAt: session?.updated_at ?? null,
        relevance,
      });
      continue;
    }

    if (hit.source === "files") {
      if (ctx.selectedPageId && hit.ref !== ctx.selectedPageId) continue;
      if (ctx.selectedFolderId) {
        const page = ctx.pagesById.get(hit.ref);
        if (!page?.folder_id || !ctx.folderIds.has(page.folder_id)) continue;
      }
      results.push({
        id: hit.ref,
        kind: "Page",
        title: hit.name || hit.ref,
        href: `/p/${hit.ref}`,
        sourceName: ctx.sourceName,
        detail: contextSnippet(snippet, query) ?? "Page",
        updatedAt: hit.date_modified ?? null,
        relevance,
      });
      continue;
    }

    results.push({
      id: `${hit.source}:${hit.ref}`,
      kind: "Source",
      title: hit.name || hit.ref,
      href: null,
      external: { source: hit.source, ref: hit.ref, name: hit.name },
      sourceName: hit.source_name ?? "Connected source",
      detail: contextSnippet(snippet, query) ?? hit.ref,
      updatedAt: hit.date_modified ?? null,
      relevance,
    });
  }
  return results;
}

// Marker entries (a dead source, a provider result cap) become notice lines so
// "reconnect me" and "there was more" never read as "no matches."
function markerNotices(hits: SourceSearchHit[]): string[] {
  const notices: string[] = [];
  for (const hit of hits) {
    const label = hit.source_name ?? hit.source;
    if (hit.error) notices.push(`${label}: ${hit.error}`);
    if (hit.truncated) {
      const total = hit.estimated_total ? ` of ~${hit.estimated_total}` : "";
      notices.push(`${label}: showing the first ${hit.returned}${total} matches.`);
    }
  }
  return notices;
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
      href: `/sessions/${encodeURIComponent(sessionId)}`,

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
      href: `/tables/${table.id}`,
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
  const slug = encodeURIComponent(detail.skill.slug);

  if (scope.includePages) {
    for (const page of detail.contents.pages) {
      if (!textIncludes(query, page.name, page.content_markdown, page.content_html)) continue;
      results.push({
        id: page.id,
        kind: "Page",
        title: page.name,
        href: `/p/${page.id}?skill=${slug}`,
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
        href: `/tables/${table.id}?skill=${slug}`,
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
    return timeValue(b.updatedAt) - timeValue(a.updatedAt);
  });
}

function timeValue(iso: string | null): number {
  return iso ? new Date(iso).getTime() : 0;
}

function scoreSessionEvent(query: string, sessionId: string, event: SessionEvent): number {
  return scoreValues(query, [
    { value: sessionId, weight: 8 },
    { value: event.agent_name, weight: 3 },
    { value: event.tool_name, weight: 2 },
    { value: event.content, weight: 1 },
  ]);
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

// The server already windows each snippet around the first query occurrence
// (with "\u2026" edge markers); this only highlights the matches within it.
// Returns null when the snippet is empty so callers can fall back to their
// default detail string.
function contextSnippet(
  source: string | null | undefined,
  query: string
): ReactNode | null {
  const text = (source ?? "").replace(/\s+/g, " ").trim();
  const trimmed = query.trim();
  if (!text) return null;
  if (!trimmed) return text;
  return highlightAll(text, trimmed);
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
