"use client";

import { useParams, useRouter, useSearchParams } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import AppShell from "../../../../components/AppShell";
import { useAuth } from "../../../../hooks/useAuth";
import {
  getDeck,
  getPersonalDeck,
  updateDeck,
  updatePersonalDeck,
  deleteDeck,
  deletePersonalDeck,
  createDeckShare,
  listDeckShares,
} from "../../../../lib/api";
import { Deck, DeckShare } from "../../../../lib/types";

export default function DeckEditorPage() {
  const params = useParams();
  const searchParams = useSearchParams();
  const router = useRouter();
  const deckId = params.deckId as string;
  const workspaceId = searchParams.get("workspaceId");
  const { user, loading, logout } = useAuth();

  const [deck, setDeck] = useState<Deck | null>(null);
  const [html, setHtml] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [showPreview, setShowPreview] = useState(false);
  const [shares, setShares] = useState<DeckShare[]>([]);
  const [showShares, setShowShares] = useState(false);
  const [editingName, setEditingName] = useState(false);
  const [nameInput, setNameInput] = useState("");

  const loadDeck = useCallback(async () => {
    try {
      if (workspaceId) {
        const d = await getDeck(workspaceId, deckId);
        setDeck(d);
        setHtml(d.html_content);
      } else {
        // Try personal first, then fall back to searching workspace decks
        try {
          const d = await getPersonalDeck(deckId);
          setDeck(d);
          setHtml(d.html_content);
        } catch {
          // Not a personal deck — it might be a workspace deck accessed without workspaceId
          // Try to load via the all-decks aggregate to find the workspace
          const { listAllDecks } = await import("../../../../lib/api");
          const all = await listAllDecks();
          const match = all?.decks?.find((d) => d.id === deckId);
          if (match && match.workspace_id) {
            const d = await getDeck(match.workspace_id, deckId);
            setDeck(d);
            setHtml(d.html_content);
          } else {
            setError("Deck not found");
          }
        }
      }
    } catch { setError("Deck not found"); }
  }, [deckId, workspaceId]);

  const loadShares = useCallback(async () => {
    try {
      const res = await listDeckShares(deckId, workspaceId || undefined);
      setShares(res?.shares ?? []);
    } catch { /* ignore */ }
  }, [deckId, workspaceId]);

  useEffect(() => { if (user) { loadDeck(); loadShares(); } }, [user, loadDeck, loadShares]);

  const handleSave = async () => {
    setSaving(true);
    try {
      const updated = workspaceId
        ? await updateDeck(workspaceId, deckId, { html_content: html })
        : await updatePersonalDeck(deckId, { html_content: html });
      setDeck(updated);
    } catch (err) { setError(err instanceof Error ? err.message : "Failed to save"); }
    setSaving(false);
  };

  const handleDelete = async () => {
    if (!confirm("Delete this deck? This cannot be undone.")) return;
    try {
      if (workspaceId) {
        await deleteDeck(workspaceId, deckId);
      } else {
        await deletePersonalDeck(deckId);
      }
      router.push("/decks");
    } catch (err) { setError(err instanceof Error ? err.message : "Failed to delete"); }
  };

  const handleNameSave = async () => {
    const trimmed = nameInput.trim();
    if (!trimmed || trimmed === deck?.name) { setEditingName(false); return; }
    try {
      const updated = workspaceId
        ? await updateDeck(workspaceId, deckId, { name: trimmed })
        : await updatePersonalDeck(deckId, { name: trimmed });
      setDeck(updated);
    } catch (err) { setError(err instanceof Error ? err.message : "Failed to rename"); }
    setEditingName(false);
  };

  const handleCreateShare = async () => {
    try {
      await createDeckShare(deckId, workspaceId || undefined);
      await loadShares();
    } catch (err) { setError(err instanceof Error ? err.message : "Failed to create share link"); }
  };

  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key === "s") {
        e.preventDefault();
        handleSave();
      }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  });

  if (loading) return <div className="min-h-screen flex items-center justify-center text-muted">Loading...</div>;
  if (!user) { router.push("/login"); return null; }

  return (
    <AppShell user={user} onLogout={logout}>
      <div className="flex flex-col h-full">
        {/* Toolbar */}
        <div className="bg-surface border-b border-border px-4 py-2 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <a href="/decks" className="text-dim hover:text-foreground text-sm">&larr;</a>
            {editingName ? (
              <input
                autoFocus
                value={nameInput}
                onChange={(e) => setNameInput(e.target.value)}
                onBlur={handleNameSave}
                onKeyDown={(e) => { if (e.key === "Enter") handleNameSave(); if (e.key === "Escape") setEditingName(false); }}
                className="bg-raised border border-border rounded px-2 py-0.5 text-sm text-foreground font-medium focus:outline-none focus:border-brand"
              />
            ) : (
              <button
                onClick={() => { setNameInput(deck?.name || ""); setEditingName(true); }}
                className="text-foreground font-medium text-sm hover:text-brand transition-colors"
                title="Click to rename"
              >
                {deck?.name || "Loading..."}
              </button>
            )}
          </div>
          <div className="flex items-center gap-2">
            <button onClick={handleDelete} className="text-xs text-red-400 hover:text-red-300 px-2 py-1">Delete</button>
            <button
              onClick={() => setShowPreview(!showPreview)}
              className={`text-xs px-3 py-1 rounded border ${showPreview ? "bg-brand border-brand text-foreground" : "bg-raised border-border text-dim"}`}
            >
              {showPreview ? "Editor" : "Preview"}
            </button>
            <button
              onClick={() => setShowShares(!showShares)}
              className="text-xs bg-raised border border-border text-dim px-3 py-1 rounded hover:text-foreground"
            >
              Share
            </button>
            <button
              onClick={handleSave}
              disabled={saving}
              className="text-xs bg-brand hover:bg-brand-hover text-foreground px-3 py-1 rounded disabled:opacity-50"
            >
              {saving ? "Saving..." : "Save"}
            </button>
          </div>
        </div>

        {error && (
          <div className="bg-red-900/30 border-b border-red-800 text-red-400 text-sm px-4 py-2">
            {error}<button onClick={() => setError("")} className="ml-2 text-red-500 hover:text-red-300">&times;</button>
          </div>
        )}

        {/* Share links panel */}
        {showShares && (
          <div className="bg-surface border-b border-border px-4 py-3">
            <div className="flex items-center justify-between mb-2">
              <span className="text-xs font-medium text-muted uppercase tracking-wider">Share Links</span>
              <button onClick={handleCreateShare} className="text-xs text-brand hover:text-brand-hover">+ New Link</button>
            </div>
            {shares.length === 0 ? (
              <p className="text-xs text-muted">No share links yet.</p>
            ) : (
              <div className="space-y-1">
                {shares.map((s) => (
                  <div key={s.id} className="flex items-center justify-between text-xs bg-raised px-2 py-1.5 rounded">
                    <code className="text-foreground font-mono select-all">
                      {typeof window !== "undefined" ? `${window.location.origin}/d/${s.token}` : `/d/${s.token}`}
                    </code>
                    <span className={`px-1.5 py-0.5 rounded ${s.is_active ? "text-green-400 bg-green-900/20" : "text-red-400 bg-red-900/20"}`}>
                      {s.is_active ? "Active" : "Inactive"}
                    </span>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}

        {/* Editor / Preview */}
        <div className="flex-1 overflow-hidden">
          {showPreview ? (
            <iframe
              srcDoc={html}
              className="w-full h-full border-0 bg-white"
              sandbox="allow-scripts allow-same-origin"
              title="Deck preview"
            />
          ) : (
            <textarea
              value={html}
              onChange={(e) => setHtml(e.target.value)}
              className="w-full h-full bg-background text-foreground font-mono text-sm p-4 resize-none focus:outline-none"
              placeholder="Write your HTML/JS/CSS here..."
              spellCheck={false}
            />
          )}
        </div>
      </div>
    </AppShell>
  );
}
