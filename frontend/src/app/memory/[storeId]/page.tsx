"use client";

import { useParams, useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import AppShell from "../../../components/AppShell";
import { useAuth } from "../../../hooks/useAuth";
import {
  getPersonalHistory,
  queryPersonalHistoryEvents,
  searchPersonalHistoryEvents,
} from "../../../lib/api";
import { HistoryEvent, History } from "../../../lib/types";

export default function HistoryDetailPage() {
  const params = useParams();
  const router = useRouter();
  const storeId = params.storeId as string;
  const { user, loading, logout } = useAuth();

  const [store, setStore] = useState<History | null>(null);
  const [events, setEvents] = useState<HistoryEvent[]>([]);
  const [hasMore, setHasMore] = useState(false);
  const [searchQuery, setSearchQuery] = useState("");
  const [filterAgent, setFilterAgent] = useState("");
  const [filterType, setFilterType] = useState("");
  const [error, setError] = useState("");

  const loadStore = useCallback(async () => {
    try {
      const s = await getPersonalHistory(storeId);
      setStore(s);
    } catch {
      setError("Store not found");
    }
  }, [storeId]);

  const loadEvents = useCallback(async () => {
    try {
      if (searchQuery.trim()) {
        const res = await searchPersonalHistoryEvents(storeId, searchQuery.trim());
        setEvents(res.events);
        setHasMore(res.has_more);
      } else {
        const res = await queryPersonalHistoryEvents(storeId, {
          agent_name: filterAgent || undefined,
          event_type: filterType || undefined,
        });
        setEvents(res.events);
        setHasMore(res.has_more);
      }
    } catch {
      // ignore
    }
  }, [storeId, searchQuery, filterAgent, filterType]);

  useEffect(() => {
    if (user) {
      loadStore();
      loadEvents();
    }
  }, [user, loadStore, loadEvents]);

  if (loading) {
    return <div className="min-h-screen flex items-center justify-center text-muted">Loading...</div>;
  }
  if (!user) { router.push("/login"); return null; }

  return (
    <AppShell user={user} onLogout={logout}>
      <div className="bg-surface border-b border-border px-4 py-2 flex items-center gap-3">
        <a href="/memory" className="text-dim hover:text-foreground text-sm">&larr; History</a>
        <h1 className="text-foreground font-medium">{store?.name || "Loading..."}</h1>
        {store?.description && (
          <span className="text-muted text-sm hidden sm:inline">{store.description}</span>
        )}
      </div>

      {error && (
        <div className="bg-red-900/30 border-b border-red-800 text-red-400 text-sm px-4 py-2">
          {error}
          <button onClick={() => setError("")} className="ml-2 text-red-500 hover:text-red-300">&times;</button>
        </div>
      )}

      <main className="flex-1 max-w-4xl mx-auto w-full px-4 py-6">
        <div className="flex gap-2 mb-4">
          <input
            type="text"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            placeholder="Search events..."
            className="flex-1 bg-raised border border-border rounded px-3 py-1.5 text-sm text-foreground focus:outline-none focus:border-brand"
          />
          <input
            type="text"
            value={filterAgent}
            onChange={(e) => setFilterAgent(e.target.value)}
            placeholder="Agent"
            className="w-28 bg-raised border border-border rounded px-3 py-1.5 text-sm text-foreground focus:outline-none focus:border-brand"
          />
          <input
            type="text"
            value={filterType}
            onChange={(e) => setFilterType(e.target.value)}
            placeholder="Type"
            className="w-28 bg-raised border border-border rounded px-3 py-1.5 text-sm text-foreground focus:outline-none focus:border-brand"
          />
        </div>

        <div className="text-xs text-muted mb-3">
          {events.length} event{events.length !== 1 ? "s" : ""}
          {hasMore && " (more available)"}
        </div>

        {events.length === 0 ? (
          <p className="text-muted text-sm">No events yet.</p>
        ) : (
          <div className="space-y-2">
            {events.map((evt) => (
              <div key={evt.id} className="bg-surface border border-border rounded-lg p-3">
                <div className="flex items-center gap-2 mb-1">
                  <span className="text-xs font-medium text-brand">{evt.agent_name}</span>
                  <span className="text-xs bg-raised text-muted px-1.5 py-0.5 rounded">{evt.event_type}</span>
                  {evt.session_id && (
                    <span className="text-xs text-muted">session: {evt.session_id}</span>
                  )}
                  {evt.tool_name && (
                    <span className="text-xs text-muted">tool: {evt.tool_name}</span>
                  )}
                  <span className="text-xs text-muted ml-auto">
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
      </main>
    </AppShell>
  );
}
