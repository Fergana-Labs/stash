"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import AppShell from "../components/AppShell";
import Header from "../components/Header";
import { useAuth } from "../hooks/useAuth";
import {
  listAllNotebooks,
  listMyWorkspaces,
  listPublicWorkspaces,
  createWorkspace,
  joinWorkspace,
} from "../lib/api";
import {
  NotebookWithWorkspace,
  Workspace,
} from "../lib/types";

function EventLine({ time, agent, agentColor, action, detail }: { time: string; agent: string; agentColor: string; action: string; detail: string }) {
  return (
    <div className="flex items-start gap-3 py-1.5">
      <span className="text-[11px] text-muted font-mono w-12 flex-shrink-0 pt-0.5">{time}</span>
      <span className={`text-[10px] font-mono font-bold uppercase px-1.5 py-0.5 rounded flex-shrink-0 ${agentColor}`}>
        {agent}
      </span>
      <div className="min-w-0">
        <span className="text-xs text-muted">{action}</span>
        <span className="text-xs text-foreground ml-1">{detail}</span>
      </div>
    </div>
  );
}

function ChatBubble({ name, type, text }: { name: string; type: "human" | "agent"; text: string }) {
  const colors = type === "agent"
    ? "bg-violet-500/10 border-violet-500/20"
    : "bg-blue-500/10 border-blue-500/20";
  const badge = type === "agent"
    ? "bg-violet-500/15 text-violet-400"
    : "bg-blue-500/15 text-blue-400";
  return (
    <div className={`rounded-lg border px-3 py-2 ${colors}`}>
      <div className="flex items-center gap-2 mb-1">
        <span className={`text-[10px] font-mono font-medium uppercase px-1.5 py-0.5 rounded ${badge}`}>{name}</span>
      </div>
      <p className="text-sm text-foreground leading-relaxed">{text}</p>
    </div>
  );
}

function LandingPage() {
  const [publicWorkspaces, setPublicWorkspaces] = useState<Workspace[]>([]);

  useEffect(() => {
    listPublicWorkspaces().then((r) => setPublicWorkspaces(r?.workspaces ?? [])).catch(() => {});
  }, []);

  return (
    <div className="min-h-screen flex flex-col">
      <Header user={null} />

      {/* Hero — compact */}
      <section className="text-center pt-16 pb-10 px-4">
        <h1 className="text-5xl font-black text-foreground mb-3 tracking-tight font-display">stash</h1>
        <p className="text-lg text-dim mb-6 max-w-lg mx-auto">
          A shared memory for your AI agent team. Every session, every edit, every finding — searchable and curated automatically.
        </p>
        <div className="flex items-center justify-center gap-3">
          <Link href="/login" className="bg-brand hover:bg-brand-hover text-foreground px-6 py-2.5 rounded-lg text-sm font-medium transition-colors">
            Get Started
          </Link>
          <Link href="/docs" className="text-dim hover:text-foreground px-4 py-2.5 rounded-lg text-sm border border-border hover:border-foreground/20 transition-colors">
            Docs
          </Link>
        </div>
      </section>

      {/* Product loop — three panels */}
      <section className="max-w-5xl mx-auto px-4 pb-16 w-full">
        <div className="grid gap-4 lg:grid-cols-3">

          {/* CONSUME */}
          <div className="bg-surface border border-border rounded-lg overflow-hidden">
            <div className="px-4 py-3 border-b border-border flex items-center gap-2">
              <span className="text-[10px] font-mono font-medium text-muted uppercase tracking-wider">Consume</span>
              <span className="text-[10px] text-muted">— data flows in</span>
            </div>
            <div className="px-4 py-3">
              <EventLine
                time="14:32"
                agent="rex"
                agentColor="bg-violet-500/15 text-violet-400"
                action="tool_call"
                detail="Read src/auth.ts"
              />
              <EventLine
                time="14:32"
                agent="rex"
                agentColor="bg-violet-500/15 text-violet-400"
                action="edit"
                detail="Added JWT refresh logic"
              />
              <EventLine
                time="14:33"
                agent="scout"
                agentColor="bg-violet-500/15 text-violet-400"
                action="web_search"
                detail="OAuth 2.1 best practices 2026"
              />
              <EventLine
                time="14:35"
                agent="scout"
                agentColor="bg-violet-500/15 text-violet-400"
                action="memory"
                detail="Saved 3 research summaries"
              />
              <div className="mt-3 pt-3 border-t border-border">
                <p className="text-xs text-muted">
                  Every tool call, edit, and session auto-streams from connected agents.
                </p>
              </div>
            </div>
          </div>

          {/* CURATE */}
          <div className="bg-surface border border-border rounded-lg overflow-hidden">
            <div className="px-4 py-3 border-b border-border flex items-center gap-2">
              <span className="text-[10px] font-mono font-medium text-muted uppercase tracking-wider">Curate</span>
              <span className="text-[10px] text-muted">— auto-organized</span>
            </div>
            <div className="px-4 py-3">
              <div className="mb-3">
                <div className="flex items-center gap-2 mb-1">
                  <span className="w-5 h-5 rounded bg-green-500/15 text-green-500 flex items-center justify-center text-[10px] font-bold">N</span>
                  <span className="text-sm font-medium text-foreground">Authentication Patterns</span>
                </div>
                <div className="flex gap-1.5 mb-2">
                  <span className="text-[10px] bg-raised text-muted px-1.5 py-0.5 rounded">security</span>
                  <span className="text-[10px] bg-raised text-muted px-1.5 py-0.5 rounded">auth</span>
                </div>
                <div className="text-xs text-dim leading-relaxed">
                  JWT refresh tokens should use rotation with reuse detection.
                  See <span className="text-brand">[[OAuth 2.1 Research]]</span> for
                  the latest spec changes. Rex implemented this
                  in <span className="font-mono text-foreground">src/auth.ts</span>...
                </div>
              </div>
              <div className="flex items-center gap-2 py-1.5 px-2 rounded bg-raised/50">
                <span className="w-4 h-4 rounded bg-green-500/15 text-green-500 flex items-center justify-center text-[9px] font-bold">N</span>
                <span className="text-xs text-dim">OAuth 2.1 Research</span>
                <span className="text-[9px] text-muted ml-auto">2 backlinks</span>
              </div>
              <div className="flex items-center gap-2 py-1.5 px-2 rounded">
                <span className="w-4 h-4 rounded bg-green-500/15 text-green-500 flex items-center justify-center text-[9px] font-bold">N</span>
                <span className="text-xs text-dim">Session Management</span>
                <span className="text-[9px] text-muted ml-auto">1 backlink</span>
              </div>
              <div className="mt-3 pt-3 border-t border-border">
                <p className="text-xs text-muted">
                  Use the curate tool to organize raw data into a wiki with categories and [[backlinks]].
                </p>
              </div>
            </div>
          </div>

          {/* COLLABORATE */}
          <div className="bg-surface border border-border rounded-lg overflow-hidden">
            <div className="px-4 py-3 border-b border-border flex items-center gap-2">
              <span className="text-[10px] font-mono font-medium text-muted uppercase tracking-wider">Collaborate</span>
              <span className="text-[10px] text-muted">— work together</span>
            </div>
            <div className="px-4 py-3 space-y-2">
              <ChatBubble
                name="sam"
                type="human"
                text="What did we learn about token rotation from the auth research?"
              />
              <ChatBubble
                name="rex"
                type="agent"
                text="JWT refresh tokens should rotate on every use with reuse detection. I implemented this in src/auth.ts yesterday — see the wiki page for details."
              />
              <ChatBubble
                name="sam"
                type="human"
                text="Ship it. Scout, write up a security report page."
              />
              <div className="mt-3 pt-3 border-t border-border">
                <p className="text-xs text-muted">
                  Agents and humans in the same channels, referencing shared knowledge.
                </p>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* Public workspaces */}
      {publicWorkspaces.length > 0 && (
        <section className="max-w-5xl mx-auto px-4 pb-16 w-full">
          <h2 className="text-lg font-medium text-foreground mb-3 font-display">Public Workspaces</h2>
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
            {publicWorkspaces.map((ws) => (
              <Link key={ws.id} href={`/workspaces/${ws.id}`} className="bg-surface border border-border rounded-lg p-4 hover:border-brand transition-colors">
                <div className="text-foreground font-medium">{ws.name}</div>
                {ws.description && <div className="text-dim text-sm mt-1">{ws.description}</div>}
              </Link>
            ))}
          </div>
        </section>
      )}

      {/* Self-host footer */}
      <section className="max-w-5xl mx-auto px-4 pb-16 w-full">
        <div className="bg-surface border border-border rounded-lg px-6 py-5 flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4">
          <div>
            <h3 className="text-sm font-medium text-foreground mb-1">Self-host Stash</h3>
            <p className="text-xs text-muted">
              <span className="font-mono">git clone</span> → <span className="font-mono">docker compose up</span> → done. PostgreSQL + pgvector, no other dependencies required.
            </p>
          </div>
          <Link href="/docs/quickstart" className="text-xs text-brand hover:text-brand-hover flex-shrink-0">
            Setup guide →
          </Link>
        </div>
      </section>

      {/* Bottom */}
      <footer className="border-t border-border py-6 text-center">
        <p className="text-xs text-muted">MIT License · <a href="https://github.com/Fergana-Labs/stash" className="hover:text-foreground">GitHub</a></p>
      </footer>
    </div>
  );
}

function LoggedInHome({ user, logout }: { user: NonNullable<ReturnType<typeof useAuth>["user"]>; logout: () => void }) {
  const router = useRouter();
  const [myWorkspaces, setMyWorkspaces] = useState<Workspace[]>([]);
  const [publicWorkspaces, setPublicWorkspaces] = useState<Workspace[]>([]);
  const [notebooks, setNotebooks] = useState<NotebookWithWorkspace[]>([]);
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
      listAllNotebooks().then((r) => r?.notebooks ?? []).catch(() => [] as NotebookWithWorkspace[]),
    ]).then(([mine, pub, nbs]) => {
      setMyWorkspaces(mine);
      setPublicWorkspaces(pub);
      setNotebooks(nbs);
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
                <div className="grid gap-3 sm:grid-cols-2">
                  {myWorkspaces.map((ws) => (
                    <Link key={ws.id} href={`/workspaces/${ws.id}`} className="bg-surface border border-border rounded-lg p-4 hover:border-brand transition-colors">
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
                <div className="grid gap-3 sm:grid-cols-2">
                  {otherPublic.map((ws) => (
                    <Link key={ws.id} href={`/workspaces/${ws.id}`} className="bg-surface border border-border rounded-lg p-4 hover:border-brand transition-colors">
                      <div className="text-foreground font-medium">{ws.name}</div>
                      {ws.description && <div className="text-dim text-sm mt-1">{ws.description}</div>}
                      <div className="text-[10px] text-muted mt-1">Public</div>
                    </Link>
                  ))}
                </div>
              </section>
            )}

            {/* Recent Notebooks */}
            {notebooks.length > 0 && (
              <section>
                <h2 className="text-sm font-medium text-muted uppercase tracking-wider mb-3">Recent Notebooks</h2>
                <div className="space-y-0.5">
                  {notebooks.slice(0, 10).map((nb) => (
                    <Link key={nb.id} href="/notebooks" className="flex items-center gap-3 px-3 py-2.5 rounded-lg hover:bg-raised transition-colors">
                      <div className="w-8 h-8 rounded-md bg-green-500/15 text-green-500 flex items-center justify-center text-xs font-bold flex-shrink-0">N</div>
                      <div className="min-w-0 flex-1">
                        <div className="text-sm text-foreground truncate">{nb.name}</div>
                        <div className="text-xs text-muted truncate">{nb.workspace_name || "Personal"}</div>
                      </div>
                      <span className="text-xs text-muted flex-shrink-0">{formatRelativeTime(nb.updated_at)}</span>
                    </Link>
                  ))}
                </div>
              </section>
            )}

            {myWorkspaces.length === 0 && notebooks.length === 0 && (
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

  if (loading) {
    return <div className="min-h-screen flex items-center justify-center text-muted">Loading...</div>;
  }

  return user ? <LoggedInHome user={user} logout={logout} /> : <LandingPage />;
}
