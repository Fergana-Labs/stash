"use client";

import { useParams, useRouter, useSearchParams } from "next/navigation";
import { useCallback, useEffect, useMemo, useState } from "react";
import AppShell from "../../../components/AppShell";
import { useAuth } from "../../../hooks/useAuth";
import {
  getHistory,
  listAllHistories,
  queryHistoryEvents,
  searchHistoryEvents,
  deleteHistory,
} from "../../../lib/api";
import { HistoryEvent, History, HistoryWithWorkspace } from "../../../lib/types";

/* ── helpers ── */

interface SessionGroup {
  sessionId: string;
  agentName: string;
  events: HistoryEvent[];
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

function buildGroups(events: HistoryEvent[]): AgentGroup[] {
  const agentMap = new Map<string, Map<string, HistoryEvent[]>>();

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

export default function HistoryDetailPage() {
  const params = useParams();
  const searchParams = useSearchParams();
  const router = useRouter();
  const storeId = params.storeId as string;
  const { user, loading, logout } = useAuth();

  const [store, setStore] = useState<History | null>(null);
  const [events, setEvents] = useState<HistoryEvent[]>([]);
  const [hasMore, setHasMore] = useState(false);
  const [searchQuery, setSearchQuery] = useState("");
  const [error, setError] = useState("");
  const [eventsLoading, setEventsLoading] = useState(false);

  /* sidebar selection */
  const [selectedAgent, setSelectedAgent] = useState<string | null>(null);
  const [selectedSession, setSelectedSession] = useState<string | null>(null);

  const workspaceId = searchParams.get("workspaceId");
  const workspaceName = searchParams.get("workspaceName");

  const loadStore = useCallback(async () => {
    try {
      if (workspaceId) {
        const s = await getHistory(workspaceId, storeId);
        setStore(s);
        return;
      }
      const all = await listAllHistories();
      const matched = (all?.stores ?? []).find(
        (item: HistoryWithWorkspace) => item.id === storeId
      );
      if (matched) {
        setStore(matched);
        return;
      }
      throw new Error("Store not found");
    } catch {
      setError("Store not found");
    }
  }, [storeId, workspaceId]);

  const loadEvents = useCallback(async () => {
    setEventsLoading(true);
    try {
      if (searchQuery.trim()) {
        const res = await searchHistoryEvents(workspaceId, storeId, searchQuery.trim());
        setEvents(res.events);
        setHasMore(res.has_more);
      } else {
        const res = await queryHistoryEvents(workspaceId, storeId, { limit: 200 });
        setEvents(res.events);
        setHasMore(res.has_more);
      }
    } catch {
      /* ignore */
    }
    setEventsLoading(false);
  }, [storeId, workspaceId, searchQuery]);

  useEffect(() => {
    if (user) {
      loadStore();
      loadEvents();
    }
  }, [user, loadStore, loadEvents]);

  const groups = useMemo(() => buildGroups(events), [events]);

  const selectedEvents = useMemo(() => {
    if (!selectedSession) return null;
    for (const ag of groups) {
      for (const s of ag.sessions) {
        if (s.sessionId === selectedSession) return s.events;
      }
    }
    return null;
  }, [groups, selectedSession]);

  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center text-muted">
        Loading...
      </div>
    );
  }
  if (!user) {
    router.push("/login");
    return null;
  }

  return (
    <AppShell user={user} onLogout={logout}>
      {/* Top bar */}
      <div className="bg-surface border-b border-border px-4 py-2 flex items-center gap-3">
        <a
          href="/memory"
          className="text-dim hover:text-foreground text-sm transition-colors duration-[150ms]"
        >
          &larr; History
        </a>
        <h1 className="text-foreground font-medium font-display">
          {store?.name || "Loading..."}
        </h1>
        {store?.description && (
          <span className="text-muted text-sm hidden sm:inline">
            {store.description}
          </span>
        )}
        {(workspaceName || workspaceId) && (
          <span className="text-muted text-sm hidden sm:inline">
            {workspaceName || "Workspace history"}
          </span>
        )}
        {!workspaceId && (
          <button
            onClick={async () => {
              if (!confirm("Delete this history store? All events will be lost."))
                return;
              try {
                await deleteHistory(null, storeId);
                router.push("/memory");
              } catch (err) {
                setError(
                  err instanceof Error ? err.message : "Failed to delete"
                );
              }
            }}
            className="ml-auto text-[11px] text-red-400 hover:text-red-300 px-2 py-1"
          >
            Delete
          </button>
        )}
      </div>

      {error && (
        <div className="bg-red-900/30 border-b border-red-800 text-red-400 text-sm px-4 py-2">
          {error}
          <button
            onClick={() => setError("")}
            className="ml-2 text-red-500 hover:text-red-300"
          >
            &times;
          </button>
        </div>
      )}

      <div className="flex flex-1 overflow-hidden">
        {/* ── Left sidebar ── */}
        <aside className="w-[250px] flex-shrink-0 border-r border-border bg-surface overflow-y-auto">
          {/* Search */}
          <div className="px-2 py-2 border-b border-border">
            <div className="flex gap-1">
              <input
                type="text"
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && loadEvents()}
                placeholder="Search events..."
                className="flex-1 min-w-0 bg-raised border border-border rounded px-2 py-1 text-[12px] text-foreground focus:outline-none focus:border-brand"
              />
              <button
                onClick={loadEvents}
                className="bg-brand hover:bg-brand-hover text-white px-2 py-1 rounded text-[11px] flex-shrink-0"
              >
                Go
              </button>
            </div>
          </div>

          {/* "All" option */}
          <div className="px-2 pt-2">
            <button
              onClick={() => {
                setSelectedAgent(null);
                setSelectedSession(null);
              }}
              className={`w-full text-left px-2 py-1.5 rounded text-[13px] font-medium transition-colors duration-[150ms] ${
                !selectedSession && !selectedAgent
                  ? "bg-brand/15 text-brand"
                  : "text-foreground hover:bg-raised"
              }`}
            >
              All Events
              {hasMore && (
                <span className="text-[10px] text-muted ml-1">(more available)</span>
              )}
            </button>
          </div>

          {/* Agent + session tree */}
          {eventsLoading ? (
            <p className="px-3 py-2 text-[11px] text-muted">Loading...</p>
          ) : (
            <div className="px-2 py-2">
              {groups.map((ag) => (
                <div key={ag.agentName} className="mb-2">
                  <button
                    onClick={() => {
                      setSelectedAgent(
                        selectedAgent === ag.agentName ? null : ag.agentName
                      );
                      setSelectedSession(null);
                    }}
                    className={`w-full text-left flex items-center gap-1.5 px-2 py-1 rounded transition-colors duration-[150ms] ${
                      selectedAgent === ag.agentName && !selectedSession
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

                  <div className="ml-3 mt-0.5">
                    {ag.sessions.map((sess) => (
                      <button
                        key={sess.sessionId}
                        onClick={() => {
                          setSelectedAgent(ag.agentName);
                          setSelectedSession(sess.sessionId);
                        }}
                        className={`w-full text-left px-2 py-1 rounded transition-colors duration-[150ms] ${
                          selectedSession === sess.sessionId
                            ? "bg-agent-muted"
                            : "hover:bg-raised"
                        }`}
                      >
                        <p className="text-[12px] text-foreground truncate leading-tight">
                          {sess.firstContent}
                        </p>
                        <p className="text-[10px] text-muted font-mono leading-tight mt-0.5">
                          {sess.events.length} event
                          {sess.events.length !== 1 ? "s" : ""} &middot;{" "}
                          {formatTime(sess.events[0].created_at)}
                        </p>
                      </button>
                    ))}
                  </div>
                </div>
              ))}
            </div>
          )}
        </aside>

        {/* ── Main panel ── */}
        <div className="flex-1 overflow-y-auto">
          <div className="max-w-3xl mx-auto px-6 py-6">
            {selectedSession && selectedEvents ? (
              <SessionView
                events={selectedEvents}
                sessionId={selectedSession}
                agentName={selectedAgent || ""}
              />
            ) : selectedAgent ? (
              <AgentOverview
                groups={groups}
                agentName={selectedAgent}
                onSelectSession={(sid) => setSelectedSession(sid)}
              />
            ) : (
              <AllEventsView
                groups={groups}
                eventsLoading={eventsLoading}
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

function SessionView({
  events,
  sessionId,
  agentName,
}: {
  events: HistoryEvent[];
  sessionId: string;
  agentName: string;
}) {
  return (
    <div>
      <div className="mb-6">
        <h1 className="text-xl font-bold text-foreground font-display">{agentName}</h1>
        <p className="text-[11px] text-muted font-mono mt-1">
          session: {sessionId} &middot; {events.length} event
          {events.length !== 1 ? "s" : ""}
        </p>
      </div>

      <div className="space-y-1">
        {events.map((evt, i) => {
          const showTime =
            i === 0 ||
            shouldShowTimestamp(events[i - 1].created_at, evt.created_at);

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
              <StoreEventCard event={evt} />
            </div>
          );
        })}
      </div>
    </div>
  );
}

/* ── Agent overview ── */

function AgentOverview({
  groups,
  agentName,
  onSelectSession,
}: {
  groups: AgentGroup[];
  agentName: string;
  onSelectSession: (sid: string) => void;
}) {
  const ag = groups.find((g) => g.agentName === agentName);
  if (!ag) return <p className="text-muted text-sm">No data for this agent.</p>;

  return (
    <div>
      <div className="mb-6">
        <h1 className="text-xl font-bold text-foreground font-display flex items-center gap-2">
          <span className="w-2 h-2 rounded-full bg-agent" />
          {agentName}
        </h1>
        <p className="text-[11px] text-muted mt-1">
          {ag.sessions.length} session{ag.sessions.length !== 1 ? "s" : ""} &middot;{" "}
          {ag.eventCount} events
        </p>
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
            <p className="text-[11px] text-muted font-mono mt-0.5 truncate opacity-60">
              {sess.sessionId}
            </p>
          </button>
        ))}
      </div>
    </div>
  );
}

/* ── All events grouped view ── */

function AllEventsView({
  groups,
  eventsLoading,
  onSelectSession,
}: {
  groups: AgentGroup[];
  eventsLoading: boolean;
  onSelectSession: (agent: string, sid: string) => void;
}) {
  if (eventsLoading) {
    return <p className="text-muted text-sm">Loading events...</p>;
  }

  if (groups.length === 0) {
    return <p className="text-muted text-sm">No events yet.</p>;
  }

  return (
    <div>
      <h1 className="text-xl font-bold text-foreground font-display mb-6">
        All Events
      </h1>

      {groups.map((ag) => (
        <div key={ag.agentName} className="mb-6">
          <div className="flex items-center gap-2 mb-2">
            <span className="w-2 h-2 rounded-full bg-agent" />
            <h2 className="text-[15px] font-semibold text-foreground">
              {ag.agentName}
            </h2>
            <span className="text-[10px] text-muted font-mono">
              {ag.eventCount} events
            </span>
          </div>

          <div className="space-y-1.5 ml-4">
            {ag.sessions.slice(0, 5).map((sess) => (
              <button
                key={sess.sessionId}
                onClick={() => onSelectSession(ag.agentName, sess.sessionId)}
                className="w-full text-left bg-surface border border-border rounded-lg p-2.5 hover:bg-raised transition-colors duration-[150ms]"
              >
                <div className="flex items-center gap-2">
                  <span className="text-[13px] text-foreground truncate">
                    {sess.firstContent}
                  </span>
                  <span className="text-[10px] text-muted font-mono ml-auto flex-shrink-0">
                    {sess.events.length}
                  </span>
                </div>
                <p className="text-[11px] text-muted mt-0.5">{sess.timeRange}</p>
              </button>
            ))}
            {ag.sessions.length > 5 && (
              <p className="text-[11px] text-muted pl-2">
                + {ag.sessions.length - 5} more session
                {ag.sessions.length - 5 !== 1 ? "s" : ""}
              </p>
            )}
          </div>
        </div>
      ))}
    </div>
  );
}

/* ── Event card (chat-like message) ── */

function StoreEventCard({ event }: { event: HistoryEvent }) {
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
