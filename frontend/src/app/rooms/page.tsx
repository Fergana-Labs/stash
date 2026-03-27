"use client";

import { useRouter } from "next/navigation";
import { useCallback, useEffect, useMemo, useState } from "react";
import AppShell from "../../components/AppShell";
import WorkspaceCard from "../../components/RoomCard";
import { useAuth } from "../../hooks/useAuth";
import { createWorkspace, listMyWorkspaces, listPublicWorkspaces, joinWorkspace } from "../../lib/api";
import { Workspace } from "../../lib/types";

export default function WorkspacesPage() {
  const router = useRouter();
  const { user, loading, logout } = useAuth();
  const [publicWorkspaces, setPublicWorkspaces] = useState<Workspace[]>([]);
  const [myWorkspaces, setMyWorkspaces] = useState<Workspace[]>([]);
  const [showCreate, setShowCreate] = useState(false);
  const [newName, setNewName] = useState("");
  const [newDesc, setNewDesc] = useState("");
  const [isPublic, setIsPublic] = useState(false);
  const [joinCode, setJoinCode] = useState("");
  const [error, setError] = useState("");
  const myWsIds = useMemo(() => new Set(myWorkspaces.map((w) => w.id)), [myWorkspaces]);

  const loadData = useCallback(() => {
    if (!user) return;
    Promise.all([
      listPublicWorkspaces().then((r) => r?.workspaces ?? []).catch(() => [] as Workspace[]),
      listMyWorkspaces().then((r) => r?.workspaces ?? []).catch(() => [] as Workspace[]),
    ]).then(([pub, mine]) => {
      setPublicWorkspaces(pub ?? []);
      setMyWorkspaces(mine ?? []);
    });
  }, [user]);

  useEffect(() => {
    if (!loading && user) loadData();
  }, [loading, user, loadData]);

  const handleCreate = async () => {
    if (!newName.trim()) return;
    setError("");
    try {
      const ws = await createWorkspace(newName.trim(), newDesc.trim(), isPublic);
      setShowCreate(false);
      setNewName("");
      setNewDesc("");
      router.push(`/workspaces/${ws.id}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to create workspace");
    }
  };

  const handleJoin = async () => {
    if (!joinCode.trim()) return;
    setError("");
    try {
      const ws = await joinWorkspace(joinCode.trim());
      router.push(`/workspaces/${ws.id}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to join workspace");
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
          <h1 className="text-2xl font-bold text-foreground font-display">Workspaces</h1>
          <button onClick={() => setShowCreate(true)} className="text-sm bg-brand hover:bg-brand-hover text-foreground px-3 py-1.5 rounded">Create Workspace</button>
        </div>
        {error && <p className="text-red-400 text-sm mb-4">{error}</p>}
        {showCreate && (
          <div className="bg-surface border border-border rounded-lg p-4 mb-6">
            <h3 className="text-foreground font-medium mb-3">New Workspace</h3>
            <input value={newName} onChange={(e) => setNewName(e.target.value)} placeholder="Name" className="w-full bg-raised border border-border rounded px-3 py-2 text-foreground text-sm mb-2" />
            <input value={newDesc} onChange={(e) => setNewDesc(e.target.value)} placeholder="Description (optional)" className="w-full bg-raised border border-border rounded px-3 py-2 text-foreground text-sm mb-2" />
            <label className="flex items-center gap-2 text-sm text-dim mb-3"><input type="checkbox" checked={isPublic} onChange={(e) => setIsPublic(e.target.checked)} /> Public</label>
            <div className="flex gap-2">
              <button onClick={handleCreate} className="bg-brand hover:bg-brand-hover text-foreground px-4 py-1.5 rounded text-sm">Create</button>
              <button onClick={() => setShowCreate(false)} className="bg-raised text-dim px-4 py-1.5 rounded text-sm">Cancel</button>
            </div>
          </div>
        )}
        <div className="bg-surface border border-border rounded-lg p-4 mb-6">
          <h3 className="text-foreground font-medium mb-2">Join by Invite Code</h3>
          <div className="flex gap-2">
            <input value={joinCode} onChange={(e) => setJoinCode(e.target.value)} placeholder="Enter invite code" className="flex-1 bg-raised border border-border rounded px-3 py-2 text-foreground text-sm" />
            <button onClick={handleJoin} className="bg-success hover:bg-success/80 text-foreground px-4 py-1.5 rounded text-sm">Join</button>
          </div>
        </div>
        {myWorkspaces.length > 0 && (
          <section className="mb-8">
            <h2 className="text-lg font-medium text-foreground mb-3 font-display">My Workspaces</h2>
            <div className="grid gap-3 sm:grid-cols-2">{myWorkspaces.map((ws) => <WorkspaceCard key={ws.id} workspace={ws} isMember />)}</div>
          </section>
        )}
        {(() => {
          const filtered = publicWorkspaces.filter((w) => !myWsIds.has(w.id));
          if (filtered.length === 0) return null;
          return (
            <section>
              <h2 className="text-lg font-medium text-foreground mb-3 font-display">Public Workspaces</h2>
              <div className="grid gap-3 sm:grid-cols-2">{filtered.map((ws) => <WorkspaceCard key={ws.id} workspace={ws} isMember={false} />)}</div>
            </section>
          );
        })()}
      </div>
    </AppShell>
  );
}
