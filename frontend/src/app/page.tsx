"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import AppShell from "../components/AppShell";
import { useAuth } from "../hooks/useAuth";
import {
  listAllPages,
  listMyWorkspaces,
  listPublicWorkspaces,
  createWorkspace,
  joinWorkspace,
  UserPageEntry,
} from "../lib/api";
import {
  Workspace,
} from "../lib/types";

function LoggedInHome({ user, logout }: { user: NonNullable<ReturnType<typeof useAuth>["user"]>; logout: () => void }) {
  const router = useRouter();
  const [myWorkspaces, setMyWorkspaces] = useState<Workspace[]>([]);
  const [publicWorkspaces, setPublicWorkspaces] = useState<Workspace[]>([]);
  const [recentPages, setRecentPages] = useState<UserPageEntry[]>([]);
  const [loading, setLoading] = useState(true);

  // Create / join state
  const [showCreate, setShowCreate] = useState(false);
  const [newName, setNewName] = useState("");
  const [newDesc, setNewDesc] = useState("");
  const [isPublic, setIsPublic] = useState(false);
  const [joinCode, setJoinCode] = useState("");
  const [error, setError] = useState("");

  const myWsIds = useMemo(() => new Set(myWorkspaces.map((w) => w.id)), [myWorkspaces]);

  const loadData = useCallback(() => {
    setLoading(true);
    Promise.all([
      listMyWorkspaces().then((r) => r?.workspaces ?? []).catch(() => [] as Workspace[]),
      listPublicWorkspaces().then((r) => r?.workspaces ?? []).catch(() => [] as Workspace[]),
      listAllPages().then((r) => r?.pages ?? []).catch(() => [] as UserPageEntry[]),
    ]).then(([mine, pub, pgs]) => {
      setMyWorkspaces(mine);
      setPublicWorkspaces(pub);
      setRecentPages(pgs);
      setLoading(false);
    });
  }, []);

  useEffect(() => { loadData(); }, [loadData]);

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

  const otherPublic = publicWorkspaces.filter((w) => !myWsIds.has(w.id));

  return (
    <AppShell user={user} onLogout={logout}>
      <div className="max-w-4xl mx-auto w-full px-4 py-8">
        <div className="flex items-center justify-between mb-6">
          <h1 className="text-2xl font-bold text-foreground font-display">Workspaces</h1>
          <button onClick={() => setShowCreate(true)} className="text-sm bg-brand hover:bg-brand-hover text-foreground px-3 py-1.5 rounded">
            Create Workspace
          </button>
        </div>

        {error && <p className="text-red-400 text-sm mb-4">{error}<button onClick={() => setError("")} className="ml-2 text-red-500">&times;</button></p>}

        {/* Create workspace form */}
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

        {/* Join by invite code */}
        <div className="bg-surface border border-border rounded-lg p-4 mb-6">
          <h3 className="text-foreground font-medium mb-2">Join by Invite Code</h3>
          <div className="flex gap-2">
            <input value={joinCode} onChange={(e) => setJoinCode(e.target.value)} placeholder="Enter invite code" className="flex-1 bg-raised border border-border rounded px-3 py-2 text-foreground text-sm" />
            <button onClick={handleJoin} className="bg-success hover:bg-success/80 text-foreground px-4 py-1.5 rounded text-sm">Join</button>
          </div>
        </div>

        {loading ? (
          <p className="text-muted text-sm">Loading...</p>
        ) : (
          <>
            {/* My Workspaces */}
            {myWorkspaces.length > 0 && (
              <section className="mb-8">
                <h2 className="text-sm font-medium text-muted uppercase tracking-wider mb-3">My Workspaces</h2>
                <div className="grid gap-2 sm:grid-cols-2">
                  {myWorkspaces.map((ws) => (
                    <Link key={ws.id} href={`/workspaces/${ws.id}`} className="bg-surface border border-border rounded-lg p-3 hover:border-brand transition-colors">
                      <div className="text-foreground font-medium">{ws.name}</div>
                      {ws.description && <div className="text-dim text-sm mt-1">{ws.description}</div>}
                      <div className="text-[10px] text-muted mt-1">{ws.member_count ?? 0} members</div>
                    </Link>
                  ))}
                </div>
              </section>
            )}

            {/* Public Workspaces */}
            {otherPublic.length > 0 && (
              <section className="mb-8">
                <h2 className="text-sm font-medium text-muted uppercase tracking-wider mb-3">Public Workspaces</h2>
                <div className="grid gap-2 sm:grid-cols-2">
                  {otherPublic.map((ws) => (
                    <Link key={ws.id} href={`/workspaces/${ws.id}`} className="bg-surface border border-border rounded-lg p-3 hover:border-brand transition-colors">
                      <div className="text-foreground font-medium">{ws.name}</div>
                      {ws.description && <div className="text-dim text-sm mt-1">{ws.description}</div>}
                      <div className="text-[10px] text-muted mt-1">Public</div>
                    </Link>
                  ))}
                </div>
              </section>
            )}

            {/* Recent pages across workspaces */}
            {recentPages.length > 0 && (
              <section>
                <h2 className="text-sm font-medium text-muted uppercase tracking-wider mb-3">Recent Pages</h2>
                <div className="space-y-0.5">
                  {recentPages.slice(0, 10).map((p) => (
                    <Link
                      key={p.id}
                      href={`/wiki?ws=${p.workspace_id}&page=${p.id}`}
                      className="flex items-center gap-3 px-3 py-2.5 rounded-lg hover:bg-raised transition-colors"
                    >
                      <div className="w-8 h-8 rounded-md bg-green-500/15 text-green-500 flex items-center justify-center text-xs font-bold flex-shrink-0">P</div>
                      <div className="min-w-0 flex-1">
                        <div className="text-sm text-foreground truncate">{p.name}</div>
                        <div className="text-xs text-muted truncate">
                          {p.workspace_name}
                          {p.folder_path.length > 0 ? ` · ${p.folder_path.join("/")}` : ""}
                        </div>
                      </div>
                      <span className="text-xs text-muted flex-shrink-0">{formatRelativeTime(p.updated_at)}</span>
                    </Link>
                  ))}
                </div>
              </section>
            )}

            {myWorkspaces.length === 0 && recentPages.length === 0 && (
              <div className="text-center py-12">
                <p className="text-dim mb-4">Nothing here yet. Create a workspace to get started.</p>
              </div>
            )}
          </>
        )}
      </div>
    </AppShell>
  );
}

function formatRelativeTime(dateStr: string): string {
  const now = Date.now();
  const then = new Date(dateStr).getTime();
  const diffMs = now - then;
  const diffMin = Math.floor(diffMs / 60000);
  if (diffMin < 1) return "just now";
  if (diffMin < 60) return `${diffMin}m ago`;
  const diffHr = Math.floor(diffMin / 60);
  if (diffHr < 24) return `${diffHr}h ago`;
  const diffDay = Math.floor(diffHr / 24);
  if (diffDay < 30) return `${diffDay}d ago`;
  return new Date(dateStr).toLocaleDateString();
}

export default function Home() {
  const { user, loading, logout } = useAuth();
  const router = useRouter();

  useEffect(() => {
    if (!loading && !user) {
      router.replace("/login");
    }
  }, [loading, router, user]);

  if (loading || !user) {
    return <div className="min-h-screen flex items-center justify-center text-muted">Loading...</div>;
  }

  return <LoggedInHome user={user} logout={logout} />;
}
