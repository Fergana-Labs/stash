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
  agentName: string;
  events: HistoryEventWithContext[];
  firstContent: string;
  timeRange: string;
  lastTimestamp: number;
}

interface AgentGroup {
  agentName: string;
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

function buildGroups(events: HistoryEventWithContext[]): AgentGroup[] {
  const agentMap = new Map<string, Map<string, HistoryEventWithContext[]>>();

  for (const evt of events) {
    const agent = evt.agent_name || "unknown";
    const session = evt.session_id || "no-session";
    if (!agentMap.has(agent)) agentMap.set(agent, new Map());
    const sessionMap = agentMap.get(agent)!;
    if (!sessionMap.has(session)) sessionMap.set(session, []);
    sessionMap.get(session)!.push(evt);
  }

  const groups: AgentGroup[] = [];

  for (const [agentName, sessionMap] of agentMap) {
    const sessions: SessionGroup[] = [];

    for (const [sessionId, evts] of sessionMap) {
      const sorted = evts.sort(
        (a, b) => new Date(a.created_at).getTime() - new Date(b.created_at).getTime()
      );
      const first = sorted[0];
      const last = sorted[sorted.length - 1];
      sessions.push({
        sessionId,
        agentName,
        events: sorted,
        firstContent: truncate(first.content, 60),
        timeRange: `${formatTime(first.created_at)} — ${formatTimeShort(last.created_at)}`,
        lastTimestamp: new Date(last.created_at).getTime(),
      });
    }

    sessions.sort((a, b) => b.lastTimestamp - a.lastTimestamp);

    groups.push({
      agentName,
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
  const { user, loading, logout } = useAuth();
  const [events, setEvents] = useState<HistoryEventWithContext[]>([]);
  const [eventsLoading, setEventsLoading] = useState(false);

  const [hasMore, setHasMore] = useState(false);
  const [loadingMore, setLoadingMore] = useState(false);
  const [selectedAgent, setSelectedAgent] = useState<string | null>(null);
  const [selectedSession, setSelectedSession] = useState<string | null>(null);

  const fetchEvents = useCallback(
    async (before?: string) => {
      if (wsId) {
        const res = await queryWorkspaceHistoryEvents(wsId, { limit: 200, before });
        // Workspace-scoped events don't carry store/workspace labels; fill
        // workspace_id so the event list still has it available.
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
    setSelectedAgent(null);
    setSelectedSession(null);
    try {
      const { events, has_more } = await fetchEvents();
      setEvents(events);
      setHasMore(has_more);
    } catch {
      /* ignore */
    }
    setEventsLoading(false);
  }, [fetchEvents]);

  const loadMore = useCallback(async () => {
    if (!events.length || loadingMore || !hasMore) return;
    setLoadingMore(true);
    try {
      const oldest = events[events.length - 1];
      const { events: newEvents, has_more } = await fetchEvents(oldest.created_at);
      setEvents((prev) => [...prev, ...newEvents]);
      setHasMore(has_more);
    } catch {
      /* ignore */
    }
    setLoadingMore(false);
  }, [events, loadingMore, hasMore, fetchEvents]);

  useEffect(() => {
    if (user) loadEvents();
  }, [user, loadEvents]);

  const groups = useMemo(() => buildGroups(events), [events]);

  // All sessions across all agents, sorted by recency
  const allSessions = useMemo(() => {
    const sessions: SessionGroup[] = [];
    for (const ag of groups) {
      for (const s of ag.sessions) sessions.push(s);
    }
    sessions.sort((a, b) => b.lastTimestamp - a.lastTimestamp);
    return sessions;
  }, [groups]);

  const selectedEvents = useMemo(() => {
    if (!selectedSession || !selectedAgent) return null;
    const ag = groups.find((g) => g.agentName === selectedAgent);
    if (!ag) return null;
    const sess = ag.sessions.find((s) => s.sessionId === selectedSession);
    return sess?.events ?? null;
  }, [groups, selectedAgent, selectedSession]);

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
        {/* ── Sidebar: flat agent list ── */}
        <aside className="w-[250px] flex-shrink-0 border-r border-border bg-surface overflow-y-auto">
          <div className="px-3 py-3 border-b border-border">
            <h2 className="text-sm font-semibold text-foreground font-display">
              History
            </h2>
            <p className="text-[11px] text-muted mt-1">
              {events.length} events
            </p>
          </div>

          {eventsLoading ? (
            <p className="px-3 py-2 text-[11px] text-muted">Loading...</p>
          ) : (
            <div className="px-2 py-2">
              {groups.map((ag) => (
                <button
                  key={ag.agentName}
                  onClick={() => {
                    setSelectedAgent(ag.agentName);
                    setSelectedSession(null);
                  }}
                  className={`w-full text-left flex items-center gap-1.5 px-2 py-1.5 rounded transition-colors duration-[150ms] mb-0.5 ${
                    selectedAgent === ag.agentName
                      ? "bg-agent-muted"
                      : "hover:bg-raised"
                  }`}
                >
                  <span className="w-1.5 h-1.5 rounded-full bg-agent flex-shrink-0" />
                  <span className="text-[13px] font-medium text-foreground truncate">
                    {ag.agentName}
                  </span>
                  <span className="text-[10px] text-muted ml-auto font-mono">
                    {ag.eventCount}
                  </span>
                </button>
              ))}
            </div>
          )}
        </aside>

        {/* ── Main panel ── */}
        <div className="flex-1 overflow-y-auto">
          <div className="max-w-3xl mx-auto px-6 py-6">
            {selectedSession && selectedEvents ? (
              /* Session → back to agent */
              <div>
                <button
                  onClick={() => setSelectedSession(null)}
                  className="text-sm text-muted hover:text-foreground transition-colors mb-4"
                >
                  &larr; {selectedAgent}
                </button>
                <SessionView
                  events={selectedEvents}
                  sessionId={selectedSession}
                  agentName={selectedAgent || ""}
                />
              </div>
            ) : selectedAgent ? (
              /* Agent → back to recent activity */
              <div>
                <button
                  onClick={() => { setSelectedAgent(null); setSelectedSession(null); }}
                  className="text-sm text-muted hover:text-foreground transition-colors mb-4"
                >
                  &larr; Recent Activity
                </button>
                <AgentOverview
                  groups={groups}
                  agentName={selectedAgent}
                  wsId={wsId}
                  onSelectSession={(sid) => setSelectedSession(sid)}
                  onDelete={async () => {
                    if (!wsId) return;
                    try {
                      const { apiFetch } = await import("../../lib/api");
                      await apiFetch(`/api/v1/workspaces/${wsId}/memory/agents/${encodeURIComponent(selectedAgent)}`, { method: "DELETE" });
                      setSelectedAgent(null);
                      loadEvents();
                    } catch { /* ignore */ }
                  }}
                />
              </div>
            ) : (
              /* Recent activity: all sessions by recency */
              <RecentActivityView
                allSessions={allSessions}
                eventsLoading={eventsLoading}
                hasMore={hasMore}
                loadingMore={loadingMore}
                onLoadMore={loadMore}
                onSelectAgent={(agent) => { setSelectedAgent(agent); setSelectedSession(null); }}
                onSelectSession={(agent, sid) => { setSelectedAgent(agent); setSelectedSession(sid); }}
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
  agentName,
}: {
  events: HistoryEventWithContext[];
  sessionId: string;
  agentName: string;
}) {
  const [typeFilter, setTypeFilter] = useState<string>("all");
  const [toolFilter, setToolFilter] = useState<string>("all");
  const [search, setSearch] = useState("");
  const [sort, setSort] = useState<SortOrder>("oldest");
  const [visibleCount, setVisibleCount] = useState(SESSION_PAGE_SIZE);
  const sentinelRef = useRef<HTMLDivElement>(null);

  const eventTypes = useMemo(() => [...new Set(events.map((e) => e.event_type))].sort(), [events]);
  const toolNames = useMemo(() => [...new Set(events.map((e) => e.tool_name).filter(Boolean))].sort() as string[], [events]);

  const filtered = useMemo(() => {
    let result = events;
    if (typeFilter !== "all") result = result.filter((e) => e.event_type === typeFilter);
    if (toolFilter !== "all") result = result.filter((e) => e.tool_name === toolFilter);
    if (search.trim()) {
      const q = search.toLowerCase();
      result = result.filter((e) =>
        e.content.toLowerCase().includes(q) ||
        e.agent_name.toLowerCase().includes(q) ||
        (e.tool_name && e.tool_name.toLowerCase().includes(q))
      );
    }
    if (sort === "newest") result = [...result].reverse();
    return result;
  }, [events, typeFilter, toolFilter, search, sort]);

  // Reset visible count when filters change
  useEffect(() => { setVisibleCount(SESSION_PAGE_SIZE); }, [typeFilter, toolFilter, search, sort]);

  const visible = filtered.slice(0, visibleCount);
  const hasMoreEvents = visibleCount < filtered.length;

  // Infinite scroll via IntersectionObserver
  useEffect(() => {
    if (!hasMoreEvents || !sentinelRef.current) return;
    const observer = new IntersectionObserver(
      ([entry]) => { if (entry.isIntersecting) setVisibleCount((c) => c + SESSION_PAGE_SIZE); },
      { rootMargin: "200px" }
    );
    observer.observe(sentinelRef.current);
    return () => observer.disconnect();
  }, [hasMoreEvents, filtered]);

  const hasFilters = typeFilter !== "all" || toolFilter !== "all" || search.trim() !== "";

  return (
    <div>
      <div className="mb-4">
        <h1 className="text-xl font-bold text-foreground font-display">{agentName}</h1>
        <p className="text-[11px] text-muted font-mono mt-1">
          session: {sessionId} &middot; {events.length} event
          {events.length !== 1 ? "s" : ""}
          {hasFilters && ` (showing ${filtered.length})`}
        </p>
      </div>

      {/* Search + filters + sort */}
      <div className="flex items-center gap-2 mb-4 flex-wrap">
        <input
          type="text"
          placeholder="Search events..."
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          className="text-[11px] bg-surface border border-border rounded px-2 py-1 text-foreground placeholder:text-muted w-40"
        />

        <select
          value={typeFilter}
          onChange={(e) => setTypeFilter(e.target.value)}
          className="text-[11px] bg-surface border border-border rounded px-2 py-1 text-foreground"
        >
          <option value="all">All types</option>
          {eventTypes.map((t) => (
            <option key={t} value={t}>{t}</option>
          ))}
        </select>

        {toolNames.length > 0 && (
          <select
            value={toolFilter}
            onChange={(e) => setToolFilter(e.target.value)}
            className="text-[11px] bg-surface border border-border rounded px-2 py-1 text-foreground"
          >
            <option value="all">All tools</option>
            {toolNames.map((t) => (
              <option key={t} value={t}>{t}</option>
            ))}
          </select>
        )}

        <select
          value={sort}
          onChange={(e) => setSort(e.target.value as SortOrder)}
          className="text-[11px] bg-surface border border-border rounded px-2 py-1 text-foreground"
        >
          <option value="oldest">Oldest first</option>
          <option value="newest">Newest first</option>
        </select>

        {hasFilters && (
          <button
            onClick={() => { setTypeFilter("all"); setToolFilter("all"); setSearch(""); }}
            className="text-[11px] text-muted hover:text-foreground transition-colors"
          >
            Clear
          </button>
        )}
      </div>

      <div className="space-y-1">
        {visible.map((evt, i) => {
          const showTime =
            i === 0 ||
            shouldShowTimestamp(visible[i - 1].created_at, evt.created_at);

          return (
            <div key={evt.id}>
              {showTime && (
                <div className="flex items-center gap-3 my-4">
                  <div className="flex-1 h-px bg-border" />
                  <span className="text-[10px] text-muted font-mono">
                    {formatTime(evt.created_at)}
                  </span>
                  <div className="flex-1 h-px bg-border" />
                </div>
              )}
              <EventCard event={evt} />
            </div>
          );
        })}
        {filtered.length === 0 && (
          <p className="text-sm text-muted py-4">No events match the current filters.</p>
        )}
        {hasMoreEvents && <div ref={sentinelRef} className="h-8" />}
      </div>
    </div>
  );
}

/* ── Agent overview ── */

function AgentOverview({
  groups,
  agentName,
  wsId,
  onSelectSession,
  onDelete,
}: {
  groups: AgentGroup[];
  agentName: string;
  wsId: string | null;
  onSelectSession: (sid: string) => void;
  onDelete: () => void;
}) {
  const ag = groups.find((g) => g.agentName === agentName);
  if (!ag) return <p className="text-muted text-sm">No data for this agent.</p>;

  return (
    <div>
      <div className="mb-6 flex items-start justify-between">
        <div>
          <h1 className="text-xl font-bold text-foreground font-display flex items-center gap-2">
            <span className="w-2 h-2 rounded-full bg-agent" />
            {agentName}
          </h1>
          <p className="text-[11px] text-muted mt-1">
            {ag.sessions.length} session{ag.sessions.length !== 1 ? "s" : ""} &middot;{" "}
            {ag.eventCount} events
          </p>
        </div>
        <button
          onClick={() => {
            if (confirm(`Delete all ${ag.eventCount} events for "${agentName}"?`)) {
              onDelete();
            }
          }}
          className="text-xs text-red-400 hover:text-red-300 px-2 py-1 rounded hover:bg-red-400/10 transition-colors"
        >
          Delete agent
        </button>
      </div>

      <div className="space-y-2">
        {ag.sessions.map((sess) => (
          <button
            key={sess.sessionId}
            onClick={() => onSelectSession(sess.sessionId)}
            className="w-full text-left bg-surface border border-border rounded-lg p-3 hover:bg-raised transition-colors duration-[150ms]"
          >
            <div className="flex items-center gap-2">
              <span className="text-[13px] text-foreground font-medium truncate">
                {sess.firstContent}
              </span>
              <span className="text-[10px] text-muted font-mono ml-auto flex-shrink-0">
                {sess.events.length} event{sess.events.length !== 1 ? "s" : ""}
              </span>
            </div>
            <p className="text-[11px] text-muted mt-1">{sess.timeRange}</p>
          </button>
        ))}
      </div>
    </div>
  );
}

/* ── Recent activity: all sessions sorted by recency ── */

const SESSIONS_PAGE_SIZE = 20;

function RecentActivityView({
  allSessions,
  eventsLoading,
  hasMore: hasMoreEvents,
  loadingMore: loadingMoreEvents,
  onLoadMore: onLoadMoreEvents,
  onSelectAgent,
  onSelectSession,
}: {
  allSessions: SessionGroup[];
  eventsLoading: boolean;
  hasMore: boolean;
  loadingMore: boolean;
  onLoadMore: () => void;
  onSelectAgent: (agent: string) => void;
  onSelectSession: (agent: string, sid: string) => void;
}) {
  const [visibleCount, setVisibleCount] = useState(SESSIONS_PAGE_SIZE);
  const sentinelRef = useRef<HTMLDivElement>(null);

  const visible = allSessions.slice(0, visibleCount);
  const hasMoreSessions = visibleCount < allSessions.length;

  // Infinite scroll — show more sessions, or fetch more events if we've shown them all.
  // The `firing` ref prevents re-entry while the sentinel is still intersecting and
  // React hasn't re-rendered the updated state yet.
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

  if (eventsLoading) {
    return <p className="text-muted text-sm">Loading events...</p>;
  }

  if (allSessions.length === 0) {
    return (
      <p className="text-muted text-sm">
        No events found. Agent activity will appear here as events are logged.
      </p>
    );
  }

  return (
    <div>
      <h1 className="text-xl font-bold text-foreground font-display mb-6">
        Recent Activity
      </h1>

      <div className="space-y-2">
        {visible.map((sess) => (
          <div
            key={`${sess.agentName}-${sess.sessionId}`}
            onClick={() => onSelectSession(sess.agentName, sess.sessionId)}
            className="w-full text-left bg-surface border border-border rounded-lg p-3 hover:bg-raised transition-colors duration-[150ms] cursor-pointer"
          >
            <div className="flex items-center gap-2">
              <button
                onClick={(e) => { e.stopPropagation(); onSelectAgent(sess.agentName); }}
                className="text-[11px] font-medium text-agent bg-agent-muted px-1.5 py-0.5 rounded font-mono uppercase tracking-[0.05em] hover:bg-agent/20 transition-colors flex-shrink-0"
              >
                {sess.agentName}
              </button>
              <span className="text-[13px] text-foreground truncate">
                {sess.firstContent}
              </span>
              <span className="text-[10px] text-muted font-mono ml-auto flex-shrink-0">
                {sess.events.length}
              </span>
            </div>
            <p className="text-[11px] text-muted mt-1">{sess.timeRange}</p>
          </div>
        ))}
      </div>

      {(hasMoreSessions || hasMoreEvents) && (
        <div ref={sentinelRef} className="h-8 flex items-center justify-center">
          {loadingMoreEvents && <span className="text-[11px] text-muted">Loading...</span>}
        </div>
      )}
    </div>
  );
}

/* ── Event card (chat-like message) ── */

function EventCard({ event }: { event: HistoryEventWithContext }) {
  return (
    <div className="flex gap-3 py-1.5">
      {/* Left border accent */}
      <div className="w-0.5 rounded-full bg-agent/40 flex-shrink-0 mt-1" />

      <div className="flex-1 min-w-0">
        {/* Header row */}
        <div className="flex items-center gap-1.5 mb-1 flex-wrap">
          <span className="text-[11px] font-medium text-agent bg-agent-muted px-1.5 py-0.5 rounded font-mono uppercase tracking-[0.05em]">
            {event.agent_name}
          </span>
          <span className="text-[11px] bg-raised text-muted px-1.5 py-0.5 rounded">
            {event.event_type}
          </span>
          {event.tool_name && (
            <span className="text-[10px] text-dim font-mono bg-raised px-1.5 py-0.5 rounded">
              {event.tool_name}
            </span>
          )}
          {event.store_name && (
            <span className="text-[10px] text-muted">in {event.store_name}</span>
          )}
          {event.workspace_name && (
            <span className="text-[10px] text-muted bg-raised px-1 py-0.5 rounded">
              {event.workspace_name}
            </span>
          )}
          <span className="text-[10px] text-muted ml-auto flex-shrink-0 font-mono">
            {formatTimeShort(event.created_at)}
          </span>
        </div>

        {/* Content */}
        <div className="text-[14px] text-foreground whitespace-pre-wrap leading-relaxed">
          {event.content}
        </div>

        {/* Metadata */}
        {Object.keys(event.metadata).length > 0 && (
          <details className="mt-1.5">
            <summary className="text-[10px] text-muted cursor-pointer hover:text-dim transition-colors duration-[150ms]">
              Metadata
            </summary>
            <pre className="text-[11px] text-dim mt-1 bg-raised p-2 rounded overflow-x-auto font-mono">
              {JSON.stringify(event.metadata, null, 2)}
            </pre>
          </details>
        )}
      </div>
    </div>
  );
}
