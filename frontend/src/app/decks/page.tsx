"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useMemo, useState } from "react";
import AppShell from "../../components/AppShell";
import { useAuth } from "../../hooks/useAuth";
import { listAllDecks, createPersonalDeck, deletePersonalDeck } from "../../lib/api";
import { DeckWithWorkspace } from "../../lib/types";

export default function DecksPage() {
  const router = useRouter();
  const { user, loading, logout } = useAuth();
  const [decks, setDecks] = useState<DeckWithWorkspace[]>([]);
  const [error, setError] = useState("");

  const loadDecks = useCallback(async () => {
    try {
      const res = await listAllDecks();
      setDecks(res?.decks ?? []);
    } catch { /* ignore */ }
  }, []);

  useEffect(() => { if (user) loadDecks(); }, [user, loadDecks]);

  const grouped = useMemo(() => {
    const groups: Record<string, { name: string; decks: DeckWithWorkspace[] }> = {};
    for (const d of decks) {
      const key = d.workspace_id || "personal";
      if (!groups[key]) groups[key] = { name: d.workspace_name || "Personal", decks: [] };
      groups[key].decks.push(d);
    }
    return groups;
  }, [decks]);

  const handleCreate = async () => {
    const name = prompt("Deck name:");
    if (!name) return;
    try {
      const deck = await createPersonalDeck(name);
      router.push(`/decks/${deck.id}/edit`);
    } catch (err) { setError(err instanceof Error ? err.message : "Failed to create deck"); }
  };

  if (loading) return <div className="min-h-screen flex items-center justify-center text-muted">Loading...</div>;
  if (!user) { router.push("/login"); return null; }

  return (
    <AppShell user={user} onLogout={logout}>
      <div className="max-w-3xl mx-auto w-full px-4 py-8">
        <div className="flex items-center justify-between mb-6">
          <h1 className="text-2xl font-bold text-foreground font-display">Decks</h1>
          <button onClick={handleCreate} className="text-sm bg-brand hover:bg-brand-hover text-foreground px-3 py-1.5 rounded">
            New Deck
          </button>
        </div>
        {error && <p className="text-red-400 text-sm mb-4">{error}</p>}
        {decks.length === 0 ? (
          <p className="text-muted text-sm">No decks yet. Create one to get started — agents can build HTML pages, slides, and dashboards.</p>
        ) : (
          Object.entries(grouped).map(([key, group]) => (
            <section key={key} className="mb-6">
              <h2 className="text-sm font-medium text-muted uppercase tracking-wider mb-2">{group.name}</h2>
              <div className="space-y-1">
                {group.decks.map((deck) => (
                  <Link
                    key={deck.id}
                    href={`/decks/${deck.id}/edit`}
                    className="group flex items-center gap-3 px-3 py-2.5 rounded-lg hover:bg-raised transition-colors"
                  >
                    <div className="w-7 h-7 rounded-md bg-brand/15 text-brand flex items-center justify-center text-xs font-bold flex-shrink-0">
                      {deck.deck_type === "slides" ? "S" : deck.deck_type === "dashboard" ? "D" : "H"}
                    </div>
                    <div className="min-w-0 flex-1">
                      <div className="text-sm text-foreground truncate">{deck.name}</div>
                      {deck.description && <div className="text-xs text-muted truncate">{deck.description}</div>}
                    </div>
                    <span className="text-[10px] text-muted bg-raised px-1.5 py-0.5 rounded flex-shrink-0">
                      {deck.deck_type}
                    </span>
                    <span className="text-xs text-muted flex-shrink-0">
                      {new Date(deck.updated_at).toLocaleDateString()}
                    </span>
                    {!deck.workspace_id && (
                      <button
                        onClick={async (e) => {
                          e.preventDefault();
                          e.stopPropagation();
                          if (!confirm("Delete this deck?")) return;
                          try {
                            await deletePersonalDeck(deck.id);
                            loadDecks();
                          } catch (err) { setError(err instanceof Error ? err.message : "Failed to delete"); }
                        }}
                        className="text-xs text-red-400 hover:text-red-300 px-2 py-1 opacity-0 group-hover:opacity-100 transition-opacity flex-shrink-0"
                      >
                        Delete
                      </button>
                    )}
                  </Link>
                ))}
              </div>
            </section>
          ))
        )}
      </div>
    </AppShell>
  );
}
