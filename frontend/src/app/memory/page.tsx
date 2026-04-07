"use client";

import { useRouter } from "next/navigation";
import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import AppShell from "../../components/AppShell";
import { useAuth } from "../../hooks/useAuth";
import {
  listAllHistories,
  listHistories,
  queryAllHistoryEvents,
  createPersonalHistory,
} from "../../lib/api";
import { HistoryEventWithContext, HistoryWithWorkspace } from "../../lib/types";

export default function MemoryPage() {
  const router = useRouter();
  const wsId = typeof window !== "undefined" ? new URLSearchParams(window.location.search).get("ws") : null;
  const { user, loading, logout } = useAuth();
  const [stores, setStores] = useState<HistoryWithWorkspace[]>([]);
  const [events, setEvents] = useState<HistoryEventWithContext[]>([]);
  const [hasMore, setHasMore] = useState(false);
  const [filterAgent, setFilterAgent] = useState("");
  const [filterType, setFilterType] = useState("");
  const [eventsLoading, setEventsLoading] = useState(false);

  const loadStores = useCallback(async () => {
    try {
      if (wsId) {
        const res = await listHistories(wsId);
        const s = (res?.stores ?? []).map((s: any) => ({ ...s, workspace_id: wsId, workspace_name: "" }));
        setStores(s);
      } else {
        const res = await listAllHistories();
        setStores(res?.stores ?? []);
      }
    } catch { /* ignore */ }
  }, [wsId]);

  const loadEvents = useCallback(async () => {
    setEventsLoading(true);
    try {
      const res = await queryAllHistoryEvents({
        agent_name: filterAgent || undefined,
        event_type: filterType || undefined,
        limit: 100,
      });
      setEvents(res?.events ?? []);
      setHasMore(res?.has_more ?? false);
    } catch { /* ignore */ }
    setEventsLoading(false);
  }, [filterAgent, filterType]);

  useEffect(() => {
    if (user) {
      loadStores();
      loadEvents();
    }
  }, [user, loadStores, loadEvents]);

  if (loading) {
    return <div className="min-h-screen flex items-center justify-center text-muted">Loading...</div>;
  }
  if (!user) { router.push("/login"); return null; }

  return (
    <AppShell user={user} onLogout={logout}>
      <div className="max-w-4xl mx-auto w-full px-4 py-8">
        <div className="flex items-center justify-between mb-6">
          <h1 className="text-2xl font-bold text-foreground font-display">History</h1>
          <div className="flex items-center gap-3">
            <span className="text-xs text-muted">
              {stores.length} store{stores.length !== 1 ? "s" : ""} across all workspaces
            </span>
            <button
              onClick={async () => {
                const name = prompt("Store name:");
                if (!name) return;
                try {
                  await createPersonalHistory(name);
                  loadStores();
                } catch { /* ignore */ }
              }}
              className="text-sm bg-brand hover:bg-brand-hover text-foreground px-3 py-1.5 rounded"
            >
              New Store
            </button>
          </div>
        </div>

        {/* Filters */}
        <div className="flex gap-2 mb-6">
          <input
            type="text"
            value={filterAgent}
            onChange={(e) => setFilterAgent(e.target.value)}
            placeholder="Filter by agent name..."
            className="flex-1 bg-raised border border-border rounded px-3 py-2 text-sm text-foreground focus:outline-none focus:border-brand"
          />
          <input
            type="text"
            value={filterType}
            onChange={(e) => setFilterType(e.target.value)}
            placeholder="Event type..."
            className="w-40 bg-raised border border-border rounded px-3 py-2 text-sm text-foreground focus:outline-none focus:border-brand"
          />
          <button
            onClick={loadEvents}
            className="bg-brand hover:bg-brand-hover text-foreground px-4 py-2 rounded text-sm"
          >
            Filter
          </button>
        </div>

        {/* Event stream */}
        {stores.length > 0 && (
          <div className="grid gap-2 sm:grid-cols-2 mb-6">
            {stores.map((store) => {
              const params = new URLSearchParams();
              if (store.workspace_id) params.set("workspaceId", store.workspace_id);
              if (store.workspace_name) params.set("workspaceName", store.workspace_name);
              const href = params.toString() ? `/memory/${store.id}?${params.toString()}` : `/memory/${store.id}`;
              return (
                <Link key={store.id} href={href} className="bg-surface border border-border rounded-lg p-3 hover:bg-raised transition-colors">
                  <div className="text-sm text-foreground">{store.name}</div>
                  <div className="text-xs text-muted mt-1">{store.workspace_name || "Personal"}</div>
                </Link>
              );
            })}
          </div>
        )}
        <div className="text-xs text-muted mb-3">
          {eventsLoading ? "Loading..." : `${events.length} event${events.length !== 1 ? "s" : ""}${hasMore ? " (more available)" : ""}`}
        </div>

        {events.length === 0 && !eventsLoading ? (
          <p className="text-muted text-sm">No events found. Agent activity will appear here as events are logged.</p>
        ) : (
          <div className="space-y-2">
            {events.map((evt) => (
              <div key={evt.id} className="bg-surface border border-border rounded-lg p-3">
                <div className="flex items-center gap-2 mb-1 flex-wrap">
                  <span className="text-xs font-medium text-agent bg-agent-muted px-1.5 py-0.5 rounded">{evt.agent_name}</span>
                  <span className="text-xs bg-raised text-muted px-1.5 py-0.5 rounded">{evt.event_type}</span>
                  {evt.store_name && (
                    <span className="text-xs text-muted">in {evt.store_name}</span>
                  )}
                  {evt.workspace_name && (
                    <span className="text-[10px] text-muted bg-raised px-1.5 py-0.5 rounded">{evt.workspace_name}</span>
                  )}
                  {evt.session_id && (
                    <span className="text-xs text-muted font-mono">session:{evt.session_id}</span>
                  )}
                  {evt.tool_name && (
                    <span className="text-xs text-muted font-mono">tool:{evt.tool_name}</span>
                  )}
                  <span className="text-xs text-muted ml-auto flex-shrink-0">
                    {new Date(evt.created_at).toLocaleString()}
                  </span>
                </div>
                <div className="text-sm text-foreground whitespace-pre-wrap">{evt.content}</div>
                {Object.keys(evt.metadata).length > 0 && (
                  <details className="mt-2">
                    <summary className="text-xs text-muted cursor-pointer">Metadata</summary>
                    <pre className="text-xs text-dim mt-1 bg-raised p-2 rounded overflow-x-auto">
                      {JSON.stringify(evt.metadata, null, 2)}
                    </pre>
                  </details>
                )}
              </div>
            ))}
          </div>
        )}
      </div>
    </AppShell>
  );
}
