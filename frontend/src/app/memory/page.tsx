"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import AppShell from "../../components/AppShell";
import { useAuth } from "../../hooks/useAuth";
import {
  createPersonalMemoryStore,
  deletePersonalMemoryStore,
  listPersonalMemoryStores,
} from "../../lib/api";
import { MemoryStore } from "../../lib/types";

export default function PersonalMemoryPage() {
  const router = useRouter();
  const { user, loading, logout } = useAuth();
  const [stores, setStores] = useState<MemoryStore[]>([]);
  const [showCreate, setShowCreate] = useState(false);
  const [newName, setNewName] = useState("");
  const [newDesc, setNewDesc] = useState("");
  const [error, setError] = useState("");

  const loadStores = useCallback(async () => {
    try {
      const res = await listPersonalMemoryStores();
      setStores(res.stores);
    } catch {
      // ignore
    }
  }, []);

  useEffect(() => {
    if (user) loadStores();
  }, [user, loadStores]);

  const handleCreate = async () => {
    if (!newName.trim()) return;
    setError("");
    try {
      await createPersonalMemoryStore(newName.trim(), newDesc.trim());
      setShowCreate(false);
      setNewName("");
      setNewDesc("");
      await loadStores();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to create store");
    }
  };

  const handleDelete = async (storeId: string) => {
    if (!confirm("Delete this memory store and all its events?")) return;
    try {
      await deletePersonalMemoryStore(storeId);
      await loadStores();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to delete store");
    }
  };

  if (loading) {
    return <div className="min-h-screen flex items-center justify-center text-muted">Loading...</div>;
  }
  if (!user) { router.push("/login"); return null; }

  return (
    <AppShell user={user} onLogout={logout}>
      <div className="max-w-4xl mx-auto w-full px-4 py-8">
        <div className="flex items-center justify-between mb-6">
          <h1 className="text-2xl font-bold text-foreground font-display">My Memory Stores</h1>
          <button
            onClick={() => setShowCreate(true)}
            className="text-sm bg-brand hover:bg-brand-hover text-foreground px-3 py-1.5 rounded"
          >
            New Store
          </button>
        </div>

        {error && <p className="text-red-400 text-sm mb-4">{error}</p>}

        {showCreate && (
          <div className="bg-surface border border-border rounded-lg p-4 mb-6">
            <h3 className="text-foreground font-medium mb-3">New Memory Store</h3>
            <input
              value={newName}
              onChange={(e) => setNewName(e.target.value)}
              placeholder="Name"
              className="w-full bg-raised border border-border rounded px-3 py-2 text-foreground text-sm mb-2"
            />
            <input
              value={newDesc}
              onChange={(e) => setNewDesc(e.target.value)}
              placeholder="Description (optional)"
              className="w-full bg-raised border border-border rounded px-3 py-2 text-foreground text-sm mb-2"
            />
            <div className="flex gap-2">
              <button onClick={handleCreate} className="bg-brand hover:bg-brand-hover text-foreground px-4 py-1.5 rounded text-sm">Create</button>
              <button onClick={() => setShowCreate(false)} className="bg-raised text-dim px-4 py-1.5 rounded text-sm">Cancel</button>
            </div>
          </div>
        )}

        {stores.length === 0 ? (
          <p className="text-muted text-sm">No memory stores yet. Create one to get started.</p>
        ) : (
          <div className="space-y-2">
            {stores.map((store) => (
              <div key={store.id} className="bg-surface border border-border rounded-lg p-4 flex items-center justify-between">
                <Link href={`/memory/${store.id}`} className="flex-1 min-w-0">
                  <div className="text-foreground font-medium">{store.name}</div>
                  {store.description && <div className="text-dim text-sm truncate">{store.description}</div>}
                  <div className="text-muted text-xs mt-1">
                    {store.event_count ?? 0} event{(store.event_count ?? 0) !== 1 ? "s" : ""}
                  </div>
                </Link>
                <button
                  onClick={() => handleDelete(store.id)}
                  className="text-xs text-red-400 hover:text-red-300 px-2 py-1 ml-3 flex-shrink-0"
                >
                  Delete
                </button>
              </div>
            ))}
          </div>
        )}
      </div>
    </AppShell>
  );
}
