"use client";

import { useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import AppShell from "../../components/AppShell";
import { useAuth } from "../../hooks/useAuth";
import { listMyWorkspaces, universalSearch } from "../../lib/api";
import type { SearchResponse, Workspace } from "../../lib/types";

const RESOURCE_TYPES = [
  { key: "history", label: "History" },
  { key: "notebook", label: "Notebooks" },
  { key: "table", label: "Tables" },
  { key: "document", label: "Documents" },
];

export default function SearchPage() {
  const router = useRouter();
  const { user, loading, logout } = useAuth();
  const [workspaces, setWorkspaces] = useState<Workspace[]>([]);
  const [selectedWs, setSelectedWs] = useState<string>("");
  const [question, setQuestion] = useState("");
  const [selectedTypes, setSelectedTypes] = useState<Set<string>>(new Set());
  const [result, setResult] = useState<SearchResponse | null>(null);
  const [searching, setSearching] = useState(false);
  const [history, setHistory] = useState<{ q: string; a: string }[]>([]);
  const [error, setError] = useState("");

  const loadWorkspaces = useCallback(async () => {
    try {
      const res = await listMyWorkspaces();
      const ws = res?.workspaces ?? [];
      setWorkspaces(ws);
    } catch {}
  }, []);

  useEffect(() => {
    if (user) loadWorkspaces();
  }, [user, loadWorkspaces]);

  const handleSearch = async () => {
    if (!question.trim()) return;
    setSearching(true);
    setError("");
    setResult(null);
    try {
      const types = selectedTypes.size > 0 ? Array.from(selectedTypes) : undefined;
      const res = await universalSearch(
        question.trim(),
        selectedWs || undefined,
        types,
      );
      setResult(res);
      setHistory((prev) => [{ q: question.trim(), a: res.answer }, ...prev].slice(0, 20));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Search failed");
    }
    setSearching(false);
  };

  const toggleType = (key: string) => {
    setSelectedTypes((prev) => {
      const next = new Set(prev);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });
  };

  if (loading) return <div className="min-h-screen flex items-center justify-center text-muted">Loading...</div>;
  if (!user) { router.push("/login"); return null; }

  return (
    <AppShell user={user} onLogout={logout}>
      <div className="max-w-3xl mx-auto w-full px-4 py-8">
        <h1 className="text-2xl font-bold text-foreground font-display mb-6">Search</h1>

        {/* Search Controls */}
        <div className="bg-surface border border-border rounded-lg p-4 mb-6">
          <div className="flex gap-2 mb-3">
            <input
              type="text"
              placeholder="Ask a question across all your data..."
              value={question}
              onChange={(e) => setQuestion(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && !e.shiftKey && handleSearch()}
              className="flex-1 text-sm bg-base border border-border rounded px-3 py-2.5 text-foreground placeholder:text-muted"
            />
            <button
              onClick={handleSearch}
              disabled={searching || !question.trim()}
              className="text-sm bg-brand hover:bg-brand-hover text-foreground px-4 py-2.5 rounded disabled:opacity-50 whitespace-nowrap"
            >
              {searching ? "Searching..." : "Search"}
            </button>
          </div>

          <div className="flex items-center gap-4">
            {/* Workspace scope */}
            <div className="flex items-center gap-2">
              <span className="text-xs text-muted">Scope:</span>
              <select
                value={selectedWs}
                onChange={(e) => setSelectedWs(e.target.value)}
                className="text-xs bg-base border border-border rounded px-2 py-1 text-foreground"
              >
                <option value="">All (personal)</option>
                {workspaces.map((ws) => (
                  <option key={ws.id} value={ws.id}>{ws.name}</option>
                ))}
              </select>
            </div>

            {/* Resource type filters */}
            <div className="flex items-center gap-1">
              <span className="text-xs text-muted mr-1">Sources:</span>
              {RESOURCE_TYPES.map(({ key, label }) => (
                <button
                  key={key}
                  onClick={() => toggleType(key)}
                  className={`text-xs px-2 py-0.5 rounded transition-colors ${
                    selectedTypes.has(key)
                      ? "bg-brand/15 text-brand"
                      : selectedTypes.size === 0
                        ? "bg-raised text-dim"
                        : "bg-raised text-muted"
                  }`}
                >
                  {label}
                </button>
              ))}
            </div>
          </div>
        </div>

        {error && <p className="text-red-400 text-sm mb-4">{error}</p>}

        {/* Result */}
        {searching && (
          <div className="text-center py-8">
            <div className="text-muted text-sm">Searching across your data...</div>
          </div>
        )}

        {result && !searching && (
          <div className="bg-surface border border-border rounded-lg p-5 mb-6">
            <div className="prose prose-sm max-w-none">
              <div className="text-sm text-foreground whitespace-pre-wrap leading-relaxed">
                {result.answer}
              </div>
            </div>
            {result.sources_used.length > 0 && (
              <div className="mt-4 pt-3 border-t border-border">
                <span className="text-xs text-muted">Sources: </span>
                {result.sources_used.map((s, i) => (
                  <span key={s} className="text-xs text-brand">
                    {s}{i < result.sources_used.length - 1 ? ", " : ""}
                  </span>
                ))}
              </div>
            )}
          </div>
        )}

        {/* Search History */}
        {history.length > 0 && (
          <section>
            <h2 className="text-sm font-medium text-muted uppercase tracking-wider mb-3">
              Recent Searches
            </h2>
            <div className="space-y-2">
              {history.map((h, i) => (
                <button
                  key={i}
                  onClick={() => { setQuestion(h.q); setResult({ answer: h.a, sources_used: [] }); }}
                  className="w-full text-left px-3 py-2 rounded-lg hover:bg-raised transition-colors"
                >
                  <div className="text-sm text-foreground truncate">{h.q}</div>
                  <div className="text-xs text-muted truncate mt-0.5">{h.a.slice(0, 120)}...</div>
                </button>
              ))}
            </div>
          </section>
        )}
      </div>
    </AppShell>
  );
}
