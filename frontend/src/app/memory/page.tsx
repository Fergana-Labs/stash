"use client";

import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useCallback, useEffect, useMemo, useRef, useState } from "react";
import AppShell from "../../components/AppShell";
import { useAuth } from "../../hooks/useAuth";
import {
  queryAllHistoryEvents,
  queryWorkspaceHistoryEvents,
} from "../../lib/api";
import { HistoryEventWithContext } from "../../lib/types";

/* ── helpers ── */

interface SessionGroup {
  sessionId: string;
  tagName: string;
  events: HistoryEventWithContext[];
  firstContent: string;
  timeRange: string;
  lastTimestamp: number;
}

interface TagGroup {
  tagName: string;
  sessions: SessionGroup[];
  eventCount: number;
}

function truncate(s: string, max: number): string {
  if (!s) return "(empty)";
  const line = s.split("\n")[0];
  return line.length > max ? line.slice(0, max) + "..." : line;
}

function formatTime(iso: string): string {
  return new Date(iso).toLocaleString(undefined, {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function formatTimeShort(iso: string): string {
  return new Date(iso).toLocaleTimeString(undefined, {
    hour: "2-digit",
    minute: "2-digit",
  });
}

function shouldShowTimestamp(a: string, b: string): boolean {
  return Math.abs(new Date(a).getTime() - new Date(b).getTime()) > 5 * 60 * 1000;
}

function buildGroups(events: HistoryEventWithContext[]): TagGroup[] {
  const tagMap = new Map<string, Map<string, HistoryEventWithContext[]>>();

  for (const evt of events) {
    const tag = evt.tag_name || "unknown";
    const session = evt.session_id || "no-session";
    if (!tagMap.has(tag)) tagMap.set(tag, new Map());
    const sessionMap = tagMap.get(tag)!;
    if (!sessionMap.has(session)) sessionMap.set(session, []);
    sessionMap.get(session)!.push(evt);
  }

  const groups: TagGroup[] = [];

  for (const [tagName, sessionMap] of tagMap) {
    const sessions: SessionGroup[] = [];

    for (const [sessionId, evts] of sessionMap) {
      const sorted = evts.sort(
        (a, b) => new Date(a.created_at).getTime() - new Date(b.created_at).getTime()
      );
      const first = sorted[0];
      const last = sorted[sorted.length - 1];
      sessions.push({
        sessionId,
        tagName,
        events: sorted,
        firstContent: truncate(first.content, 60),
        timeRange: `${formatTime(first.created_at)} — ${formatTimeShort(last.created_at)}`,
        lastTimestamp: new Date(last.created_at).getTime(),
      });
    }

    sessions.sort((a, b) => b.lastTimestamp - a.lastTimestamp);

    groups.push({
      tagName,
      sessions,
      eventCount: sessions.reduce((sum, s) => sum + s.events.length, 0),
    });
  }

  groups.sort((a, b) => {
    const aLatest = a.sessions[0]?.lastTimestamp ?? 0;
    const bLatest = b.sessions[0]?.lastTimestamp ?? 0;
    return bLatest - aLatest;
  });

  return groups;
}

/* ── role primitives ── */

type Role = "agent" | "human";

function isUserEvent(eventType: string): boolean {
  return eventType === "user_message";
}

function RoleAvatar({
  role,
  name,
  size = 24,
}: {
  role: Role;
  name: string;
  size?: number;
}) {
  return (
    <span
      className="inline-flex flex-shrink-0 items-center justify-center rounded-full font-display font-bold text-white"
      style={{
        width: size,
        height: size,
        fontSize: Math.round(size * 0.4),
        background:
          role === "agent" ? "var(--color-agent)" : "var(--color-human)",
      }}
    >
      {(name?.[0] || "?").toUpperCase()}
    </span>
  );
}

function RoleTag({ role }: { role: Role }) {
  const style =
    role === "agent"
      ? { background: "var(--color-agent-muted)", color: "var(--color-agent)" }
      : { background: "var(--color-human-muted)", color: "var(--color-human)" };
  return (
    <span
      className="inline-flex items-center rounded px-1.5 py-0.5 font-mono text-[10px] font-medium uppercase leading-none tracking-[0.08em]"
      style={style}
    >
      {role}
    </span>
  );
}

/* ── component ── */

export default function MemoryPage() {
  return (
    <Suspense fallback={null}>
      <MemoryPageInner />
    </Suspense>
  );
}

function MemoryPageInner() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const wsId = searchParams.get("ws");
  const urlAgent = searchParams.get("agent");
  const { user, loading, logout } = useAuth();
  const [events, setEvents] = useState<HistoryEventWithContext[]>([]);
  const [eventsLoading, setEventsLoading] = useState(false);

  const [hasMore, setHasMore] = useState(false);
  const [loadingMore, setLoadingMore] = useState(false);
  const [selectedTag, setSelectedAgent] = useState<string | null>(null);
  const [selectedSession, setSelectedSession] = useState<string | null>(null);

  const fetchEvents = useCallback(
    async (before?: string) => {
      if (wsId) {
        const res = await queryWorkspaceHistoryEvents(wsId, { limit: 200, before });
        const events: HistoryEventWithContext[] = (res?.events ?? []).map((e) => ({
          ...e,
          store_id: "",
          store_name: "",
          workspace_id: wsId,
          workspace_name: null,
        }));
        return { events, has_more: res?.has_more ?? false };
      }
      const res = await queryAllHistoryEvents({ limit: 200, before });
      return { events: res?.events ?? [], has_more: res?.has_more ?? false };
    },
    [wsId]
  );

  const loadEvents = useCallback(async () => {
    setEventsLoading(true);
    setSelectedAgent(urlAgent);
    setSelectedSession(null);
    try {
      const { events, has_more } = await fetchEvents();
      setEvents(events);
      setHasMore(has_more);
    } catch {}
    setEventsLoading(false);
  }, [fetchEvents, urlAgent]);

  const loadMore = useCallback(async () => {
    if (!events.length || loadingMore || !hasMore) return;
    setLoadingMore(true);
    try {
      const oldest = events[events.length - 1];
      const { events: newEvents, has_more } = await fetchEvents(oldest.created_at);
      setEvents((prev) => [...prev, ...newEvents]);
      setHasMore(has_more);
    } catch {}
    setLoadingMore(false);
  }, [events, loadingMore, hasMore, fetchEvents]);

  useEffect(() => {
    if (user) loadEvents();
  }, [user, loadEvents]);

  const groups = useMemo(() => buildGroups(events), [events]);

  const allSessions = useMemo(() => {
    const sessions: SessionGroup[] = [];
    for (const ag of groups) {
      for (const s of ag.sessions) sessions.push(s);
    }
    sessions.sort((a, b) => b.lastTimestamp - a.lastTimestamp);
    return sessions;
  }, [groups]);

  const selectedEvents = useMemo(() => {
    if (!selectedSession || !selectedTag) return null;
    const ag = groups.find((g) => g.tagName === selectedTag);
    if (!ag) return null;
    const sess = ag.sessions.find((s) => s.sessionId === selectedSession);
    return sess?.events ?? null;
  }, [groups, selectedTag, selectedSession]);

  useEffect(() => {
    if (!loading && !user) router.push("/login");
  }, [loading, user, router]);

  if (loading || !user) {
    return (
      <div className="min-h-screen flex items-center justify-center text-muted">
        Loading...
      </div>
    );
  }

  return (
    <AppShell user={user} onLogout={logout}>
      <div className="flex h-full overflow-hidden">
        {/* Sidebar: agent list */}
        <aside className="w-[250px] flex-shrink-0 overflow-y-auto border-r border-border bg-surface">
          <div className="border-b border-border-subtle px-4 py-4">
            <p className="font-mono text-[10px] font-medium uppercase tracking-[0.12em] text-muted">
              Tags
            </p>
            <p className="mt-1 font-display text-[15px] font-semibold text-foreground">
              {groups.length} tag{groups.length === 1 ? "" : "s"} · {events.length} events
            </p>
          </div>

          {eventsLoading ? (
            <p className="px-4 py-3 text-[11px] text-muted">Loading…</p>
          ) : (
            <div className="px-2 py-2">
              {groups.map((ag) => (
                <button
                  key={ag.tagName}
                  onClick={() => {
                    setSelectedAgent(ag.tagName);
                    setSelectedSession(null);
                  }}
                  className={
                    "mb-0.5 flex w-full items-center gap-2 rounded-md px-2 py-1.5 text-left transition-colors " +
                    (selectedTag === ag.tagName
                      ? "bg-agent-muted"
                      : "hover:bg-raised")
                  }
                >
                  <span
                    className="h-1.5 w-1.5 flex-shrink-0 rounded-full"
                    style={{ background: "var(--color-agent)" }}
                  />
                  <span className="truncate text-[13px] font-medium text-foreground">
                    {ag.tagName}
                  </span>
                  <span className="ml-auto font-mono text-[10px] text-muted">
                    {ag.eventCount}
                  </span>
                </button>
              ))}
              {groups.length === 0 && !eventsLoading && (
                <p className="px-2 py-2 text-[11px] text-muted">No tags yet.</p>
              )}
            </div>
          )}
        </aside>

        {/* Main */}
        <div className="flex-1 overflow-y-auto">
          <div className="mx-auto w-full max-w-[900px] px-8 py-8">
            <div className="mb-8">
              <h1 className="font-display text-[32px] font-bold tracking-[-0.02em] text-foreground">
                History
              </h1>
            </div>

            {selectedSession && selectedEvents ? (
              <div>
                <button
                  onClick={() => setSelectedSession(null)}
                  className="mb-5 text-[13px] text-muted transition-colors hover:text-foreground"
                >
                  ← {selectedTag}
                </button>
                <SessionView
                  events={selectedEvents}
                  sessionId={selectedSession}
                  tagName={selectedTag || ""}
                />
              </div>
            ) : selectedTag ? (
              <div>
                <button
                  onClick={() => {
                    setSelectedAgent(null);
                    setSelectedSession(null);
                  }}
                  className="mb-5 text-[13px] text-muted transition-colors hover:text-foreground"
                >
                  ← Recent activity
                </button>
                <TagOverview
                  groups={groups}
                  tagName={selectedTag}
                  wsId={wsId}
                  onSelectSession={(sid) => setSelectedSession(sid)}
                  onDelete={async () => {
                    if (!wsId) return;
                    try {
                      const { apiFetch } = await import("../../lib/api");
                      await apiFetch(
                        `/api/v1/workspaces/${wsId}/memory/tags/${encodeURIComponent(
                          selectedTag
                        )}`,
                        { method: "DELETE" }
                      );
                      setSelectedAgent(null);
                      loadEvents();
                    } catch {}
                  }}
                />
              </div>
            ) : (
              <RecentActivityView
                allSessions={allSessions}
                eventsLoading={eventsLoading}
                hasMore={hasMore}
                loadingMore={loadingMore}
                onLoadMore={loadMore}
                onSelectTag={(agent) => {
                  setSelectedAgent(agent);
                  setSelectedSession(null);
                }}
                onSelectSession={(agent, sid) => {
                  setSelectedAgent(agent);
                  setSelectedSession(sid);
                }}
              />
            )}
          </div>
        </div>
      </div>
    </AppShell>
  );
}

/* ── Session conversation view ── */

const SESSION_PAGE_SIZE = 50;
type SortOrder = "oldest" | "newest";

function SessionView({
  events,
  sessionId,
  tagName,
}: {
  events: HistoryEventWithContext[];
  sessionId: string;
  tagName: string;
}) {
  const [typeFilter, setTypeFilter] = useState<string>("all");
  const [toolFilter, setToolFilter] = useState<string>("all");
  const [search, setSearch] = useState("");
  const [sort, setSort] = useState<SortOrder>("oldest");
  const [visibleCount, setVisibleCount] = useState(SESSION_PAGE_SIZE);
  const sentinelRef = useRef<HTMLDivElement>(null);

  const eventTypes = useMemo(
    () => [...new Set(events.map((e) => e.event_type))].sort(),
    [events]
  );
  const toolNames = useMemo(
    () =>
      [...new Set(events.map((e) => e.tool_name).filter(Boolean))].sort() as string[],
    [events]
  );

  const filtered = useMemo(() => {
    let result = events;
    if (typeFilter !== "all") result = result.filter((e) => e.event_type === typeFilter);
    if (toolFilter !== "all") result = result.filter((e) => e.tool_name === toolFilter);
    if (search.trim()) {
      const q = search.toLowerCase();
      result = result.filter(
        (e) =>
          e.content.toLowerCase().includes(q) ||
          e.tag_name.toLowerCase().includes(q) ||
          (e.tool_name && e.tool_name.toLowerCase().includes(q))
      );
    }
    if (sort === "newest") result = [...result].reverse();
    return result;
  }, [events, typeFilter, toolFilter, search, sort]);

  useEffect(() => {
    setVisibleCount(SESSION_PAGE_SIZE);
  }, [typeFilter, toolFilter, search, sort]);

  const visible = filtered.slice(0, visibleCount);
  const hasMoreEvents = visibleCount < filtered.length;

  useEffect(() => {
    if (!hasMoreEvents || !sentinelRef.current) return;
    const observer = new IntersectionObserver(
      ([entry]) => {
        if (entry.isIntersecting) setVisibleCount((c) => c + SESSION_PAGE_SIZE);
      },
      { rootMargin: "200px" }
    );
    observer.observe(sentinelRef.current);
    return () => observer.disconnect();
  }, [hasMoreEvents, filtered]);

  const hasFilters =
    typeFilter !== "all" || toolFilter !== "all" || search.trim() !== "";

  return (
    <div>
      <header className="mb-5 flex items-center gap-3 border-b border-border-subtle pb-4">
        <RoleAvatar role="agent" name={tagName} size={32} />
        <div>
          <div className="font-display text-[16px] font-bold text-foreground">
            {tagName}
          </div>
          <div className="mt-0.5 flex items-center gap-2 font-mono text-[11px] text-muted">
            <RoleTag role="agent" />
            <span>
              session · {sessionId} · {events.length} event
              {events.length !== 1 ? "s" : ""}
              {hasFilters && ` (showing ${filtered.length})`}
            </span>
          </div>
        </div>
      </header>

      <div className="mb-5 flex flex-wrap items-center gap-2">
        <input
          type="text"
          placeholder="Search events…"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          className="w-48 rounded border border-border bg-surface px-2.5 py-1.5 text-[12px] text-foreground placeholder:text-muted focus:border-brand focus:outline-none"
        />
        <select
          value={typeFilter}
          onChange={(e) => setTypeFilter(e.target.value)}
          className="rounded border border-border bg-surface px-2.5 py-1.5 text-[12px] text-foreground"
        >
          <option value="all">All types</option>
          {eventTypes.map((t) => (
            <option key={t} value={t}>
              {t}
            </option>
          ))}
        </select>
        {toolNames.length > 0 && (
          <select
            value={toolFilter}
            onChange={(e) => setToolFilter(e.target.value)}
            className="rounded border border-border bg-surface px-2.5 py-1.5 text-[12px] text-foreground"
          >
            <option value="all">All tools</option>
            {toolNames.map((t) => (
              <option key={t} value={t}>
                {t}
              </option>
            ))}
          </select>
        )}
        <select
          value={sort}
          onChange={(e) => setSort(e.target.value as SortOrder)}
          className="rounded border border-border bg-surface px-2.5 py-1.5 text-[12px] text-foreground"
        >
          <option value="oldest">Oldest first</option>
          <option value="newest">Newest first</option>
        </select>
        {hasFilters && (
          <button
            onClick={() => {
              setTypeFilter("all");
              setToolFilter("all");
              setSearch("");
            }}
            className="font-mono text-[11px] text-muted transition-colors hover:text-foreground"
          >
            Clear
          </button>
        )}
      </div>

      <div className="flex flex-col gap-3.5">
        {visible.map((evt, i) => {
          const showTime =
            i === 0 || shouldShowTimestamp(visible[i - 1].created_at, evt.created_at);
          return (
            <div key={evt.id}>
              {showTime && (
                <div className="my-3 flex items-center gap-3">
                  <div className="h-px flex-1 bg-border-subtle" />
                  <span className="font-mono text-[10px] text-muted">
                    {formatTime(evt.created_at)}
                  </span>
                  <div className="h-px flex-1 bg-border-subtle" />
                </div>
              )}
              <EventRow event={evt} />
            </div>
          );
        })}
        {filtered.length === 0 && (
          <p className="py-4 text-[13px] text-muted">
            No events match the current filters.
          </p>
        )}
        {hasMoreEvents && <div ref={sentinelRef} className="h-8" />}
      </div>
    </div>
  );
}

/* ── Agent overview ── */

function TagOverview({
  groups,
  tagName,
  onSelectSession,
  onDelete,
}: {
  groups: TagGroup[];
  tagName: string;
  wsId: string | null;
  onSelectSession: (sid: string) => void;
  onDelete: () => void;
}) {
  const ag = groups.find((g) => g.tagName === tagName);
  if (!ag) return <p className="text-[13px] text-muted">No data for this tag.</p>;

  return (
    <div>
      <header className="mb-6 flex items-start justify-between gap-3 border-b border-border-subtle pb-4">
        <div className="flex items-center gap-3">
          <RoleAvatar role="agent" name={tagName} size={32} />
          <div>
            <div className="font-display text-[16px] font-bold text-foreground">
              {tagName}
            </div>
            <div className="mt-0.5 flex items-center gap-2 font-mono text-[11px] text-muted">
              <RoleTag role="agent" />
              <span>
                {ag.sessions.length} session{ag.sessions.length !== 1 ? "s" : ""} ·{" "}
                {ag.eventCount} events
              </span>
            </div>
          </div>
        </div>
        <button
          onClick={() => {
            if (confirm(`Delete all ${ag.eventCount} events for "${tagName}"?`)) {
              onDelete();
            }
          }}
          className="rounded px-2 py-1 text-[12px] text-red-500 transition-colors hover:bg-red-500/10"
        >
          Delete tag
        </button>
      </header>

      <div className="flex flex-col gap-2">
        {ag.sessions.map((sess) => (
          <button
            key={sess.sessionId}
            onClick={() => onSelectSession(sess.sessionId)}
            className="w-full cursor-pointer rounded-lg border border-border-subtle bg-base px-4 py-3 text-left transition-colors hover:border-brand"
          >
            <div className="flex items-center gap-2">
              <span className="truncate text-[14px] font-medium text-foreground">
                {sess.firstContent}
              </span>
              <span className="ml-auto flex-shrink-0 font-mono text-[11px] text-muted">
                {sess.events.length} event{sess.events.length !== 1 ? "s" : ""}
              </span>
            </div>
            <p className="mt-1 font-mono text-[11px] text-muted">{sess.timeRange}</p>
          </button>
        ))}
      </div>
    </div>
  );
}

/* ── Recent activity ── */

const SESSIONS_PAGE_SIZE = 20;

function RecentActivityView({
  allSessions,
  eventsLoading,
  hasMore: hasMoreEvents,
  loadingMore: loadingMoreEvents,
  onLoadMore: onLoadMoreEvents,
  onSelectTag,
  onSelectSession,
}: {
  allSessions: SessionGroup[];
  eventsLoading: boolean;
  hasMore: boolean;
  loadingMore: boolean;
  onLoadMore: () => void;
  onSelectTag: (agent: string) => void;
  onSelectSession: (agent: string, sid: string) => void;
}) {
  const [visibleCount, setVisibleCount] = useState(SESSIONS_PAGE_SIZE);
  const sentinelRef = useRef<HTMLDivElement>(null);

  const visible = allSessions.slice(0, visibleCount);
  const hasMoreSessions = visibleCount < allSessions.length;

  const firingRef = useRef(false);
  useEffect(() => {
    if (!sentinelRef.current) return;
    const observer = new IntersectionObserver(
      ([entry]) => {
        if (!entry.isIntersecting) {
          firingRef.current = false;
          return;
        }
        if (firingRef.current) return;
        if (hasMoreSessions) {
          firingRef.current = true;
          setVisibleCount((c) => c + SESSIONS_PAGE_SIZE);
        } else if (hasMoreEvents && !loadingMoreEvents) {
          firingRef.current = true;
          onLoadMoreEvents();
        }
      },
      { rootMargin: "200px" }
    );
    observer.observe(sentinelRef.current);
    return () => observer.disconnect();
  }, [hasMoreSessions, hasMoreEvents, loadingMoreEvents, onLoadMoreEvents]);

  if (eventsLoading) return <p className="text-[13px] text-muted">Loading events…</p>;

  if (allSessions.length === 0) {
    return (
      <p className="text-[13px] text-muted">
        No events found. Activity will appear here as events are logged.
      </p>
    );
  }

  return (
    <div>
      <p className="mb-4 font-mono text-[11px] font-medium uppercase tracking-[0.12em] text-muted">
        Recent activity
      </p>
      <div className="flex flex-col gap-2">
        {visible.map((sess) => (
          <div
            key={`${sess.tagName}-${sess.sessionId}`}
            onClick={() => onSelectSession(sess.tagName, sess.sessionId)}
            className="w-full cursor-pointer rounded-lg border border-border-subtle bg-base px-4 py-3 text-left transition-colors hover:border-brand"
          >
            <div className="flex items-center gap-2">
              <RoleAvatar role="agent" name={sess.tagName} size={22} />
              <button
                onClick={(e) => {
                  e.stopPropagation();
                  onSelectTag(sess.tagName);
                }}
                className="rounded font-mono text-[11px] font-medium tracking-[0.05em] text-foreground underline-offset-2 hover:underline"
              >
                {sess.tagName}
              </button>
              <RoleTag role="agent" />
              <span className="truncate text-[13px] text-dim">
                {sess.firstContent}
              </span>
              <span className="ml-auto flex-shrink-0 font-mono text-[11px] text-muted">
                {sess.events.length}
              </span>
            </div>
            <p className="mt-1.5 pl-[30px] font-mono text-[11px] text-muted">
              {sess.timeRange}
            </p>
          </div>
        ))}
      </div>

      {(hasMoreSessions || hasMoreEvents) && (
        <div
          ref={sentinelRef}
          className="flex h-8 items-center justify-center"
        >
          {loadingMoreEvents && (
            <span className="font-mono text-[11px] text-muted">Loading…</span>
          )}
        </div>
      )}
    </div>
  );
}

/* ── Event row (chat-like message, design-styled) ── */

function EventRow({ event }: { event: HistoryEventWithContext }) {
  const isUser = isUserEvent(event.event_type);
  const role: Role = isUser ? "human" : "agent";
  const displayName = isUser ? (event.created_by_name || "user") : event.tag_name;
  return (
    <div className="flex gap-3">
      <RoleAvatar role={role} name={displayName} size={24} />
      <div className="min-w-0 flex-1">
        <div className="mb-1 flex flex-wrap items-center gap-2">
          <span className="text-[12px] font-semibold text-foreground">
            {displayName}
          </span>
          <RoleTag role={role} />
          <span className="text-[11px] text-muted">·</span>
          <span className="font-mono text-[11px] text-dim">{event.event_type}</span>
          {isUser && (
            <span className="text-[11px] text-muted">
              → {event.tag_name}
            </span>
          )}
          {event.store_name && (
            <span className="text-[11px] text-muted">in {event.store_name}</span>
          )}
          {event.workspace_name && (
            <span className="rounded bg-raised px-1.5 py-0.5 font-mono text-[10px] text-dim">
              {event.workspace_name}
            </span>
          )}
          <span className="ml-auto flex-shrink-0 font-mono text-[10px] text-muted">
            {formatTimeShort(event.created_at)}
          </span>
        </div>
        <div className="whitespace-pre-wrap text-[14px] leading-[1.55] text-foreground">
          {event.content}
        </div>
        {event.tool_name && (
          <div className="mt-1.5 flex items-center gap-2 rounded border border-border-subtle bg-surface px-2.5 py-1 font-mono text-[12px] text-dim">
            <span className="text-[10px] uppercase tracking-[0.08em] text-muted">
              tool
            </span>
            {event.tool_name}
          </div>
        )}
        {Object.keys(event.metadata).length > 0 && (
          <details className="mt-1.5">
            <summary className="cursor-pointer text-[10px] text-muted transition-colors hover:text-dim">
              Metadata
            </summary>
            <pre className="mt-1 overflow-x-auto rounded bg-raised p-2 font-mono text-[11px] text-dim">
              {JSON.stringify(event.metadata, null, 2)}
            </pre>
          </details>
        )}
      </div>
    </div>
  );
}
