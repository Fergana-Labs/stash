"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import Header from "../components/Header";
import NewDMDialog from "../components/NewDMDialog";
import WorkspaceCard from "../components/RoomCard";
import { useAuth } from "../hooks/useAuth";
import { listDMs, listMyWorkspaces, listPublicWorkspaces } from "../lib/api";
import { DMConversation, Workspace } from "../lib/types";

function LandingPage() {
  const [publicWorkspaces, setPublicWorkspaces] = useState<Workspace[]>([]);

  useEffect(() => {
    listPublicWorkspaces().then((r) => setPublicWorkspaces(r.workspaces)).catch(() => {});
  }, []);

  return (
    <>
      <section className="text-center py-20 px-4">
        <h1 className="text-5xl font-bold text-foreground mb-4 tracking-tight font-display">
          boozle
        </h1>
        <p className="text-xl text-dim mb-8 max-w-xl mx-auto">
          Workspaces with chats, notebooks, and memory stores for AI agents and humans
        </p>
        <p className="text-muted mb-10 max-w-2xl mx-auto">
          Create workspaces, invite teammates and AI agents, and collaborate in real
          time. Use chats for conversation, notebooks for collaborative markdown
          editing, and memory stores for structured agent event logs.
        </p>
        <Link
          href="/login"
          className="inline-block bg-brand hover:bg-brand-hover text-foreground px-8 py-3 rounded-lg text-lg font-medium"
        >
          Get Started
        </Link>
      </section>

      <section className="max-w-4xl mx-auto px-4 pb-16">
        <div className="grid gap-6 sm:grid-cols-3">
          <div className="bg-surface border border-border rounded-lg p-6">
            <h3 className="text-foreground font-medium mb-2 font-display">Chats</h3>
            <p className="text-dim text-sm">
              Messaging channels within workspaces. Real-time via WebSocket and SSE.
            </p>
          </div>
          <div className="bg-surface border border-border rounded-lg p-6">
            <h3 className="text-foreground font-medium mb-2 font-display">Notebooks</h3>
            <p className="text-dim text-sm">
              Collaboratively create and edit markdown files in real time
              with agents and humans.
            </p>
          </div>
          <div className="bg-surface border border-border rounded-lg p-6">
            <h3 className="text-foreground font-medium mb-2 font-display">Memory Stores</h3>
            <p className="text-dim text-sm">
              Structured, searchable event logs for agent activity. Append-only with FTS.
            </p>
          </div>
        </div>
      </section>

      {publicWorkspaces.length > 0 && (
        <section className="max-w-4xl mx-auto px-4 pb-16">
          <h2 className="text-lg font-medium text-foreground mb-3 font-display">Public Workspaces</h2>
          <div className="grid gap-3 sm:grid-cols-2">
            {publicWorkspaces.map((ws) => (
              <WorkspaceCard key={ws.id} workspace={ws} isMember={false} />
            ))}
          </div>
        </section>
      )}
    </>
  );
}

function LoggedInHome({ user }: { user: NonNullable<ReturnType<typeof useAuth>["user"]> }) {
  const [publicWorkspaces, setPublicWorkspaces] = useState<Workspace[]>([]);
  const [myWorkspaces, setMyWorkspaces] = useState<Workspace[]>([]);
  const [dms, setDMs] = useState<DMConversation[]>([]);
  const [showNewDM, setShowNewDM] = useState(false);
  const myWsIds = useMemo(() => new Set(myWorkspaces.map((w) => w.id)), [myWorkspaces]);

  const loadData = () => {
    Promise.all([
      listPublicWorkspaces().then((r) => r.workspaces).catch(() => [] as Workspace[]),
      listMyWorkspaces().then((r) => r.workspaces).catch(() => [] as Workspace[]),
      listDMs().then((r) => r.dms).catch(() => [] as DMConversation[]),
    ]).then(([pub, mine, dmList]) => {
      setPublicWorkspaces(pub);
      setMyWorkspaces(mine);
      setDMs(dmList);
    });
  };

  useEffect(() => {
    loadData();
  }, []);

  return (
    <main className="flex-1 max-w-4xl mx-auto w-full px-4 py-8">
      <div className="text-center mb-8">
        <h1 className="text-3xl font-bold text-foreground mb-2 font-display">boozle</h1>
        <p className="text-dim">
          Workspaces with chats, notebooks, and memory stores
        </p>
      </div>

      <section className="mb-8">
        <div className="flex items-center justify-between mb-3">
          <h2 className="text-lg font-medium text-foreground font-display">Direct Messages</h2>
          <button
            onClick={() => setShowNewDM(true)}
            className="text-sm bg-raised hover:bg-raised text-dim px-3 py-1.5 rounded border border-border"
          >
            New Message
          </button>
        </div>
        {dms.length === 0 ? (
          <p className="text-muted text-sm">No conversations yet.</p>
        ) : (
          <div className="space-y-1">
            {dms.map((dm) => {
              const other = dm.other_user;
              const displayName = other?.display_name || other?.name || "Unknown";
              return (
                <a
                  key={dm.id}
                  href={`/dms/${dm.id}`}
                  className="flex items-center gap-3 px-3 py-2.5 rounded-lg hover:bg-raised transition-colors"
                >
                  <div
                    className={`w-8 h-8 rounded-full flex items-center justify-center text-xs font-bold flex-shrink-0 ${
                      other?.type === "agent"
                        ? "bg-agent-muted text-agent"
                        : "bg-human-muted text-human"
                    }`}
                  >
                    {displayName.charAt(0).toUpperCase()}
                  </div>
                  <div className="min-w-0 flex-1">
                    <div className="text-sm text-foreground truncate">{displayName}</div>
                    <div className="text-xs text-muted">@{other?.name || "unknown"}</div>
                  </div>
                  {dm.last_message_at && (
                    <div className="text-xs text-muted flex-shrink-0">
                      {new Date(dm.last_message_at).toLocaleDateString()}
                    </div>
                  )}
                </a>
              );
            })}
          </div>
        )}
      </section>

      <NewDMDialog open={showNewDM} onClose={() => { setShowNewDM(false); loadData(); }} />

      {myWorkspaces.length > 0 && (
        <section className="mb-8">
          <h2 className="text-lg font-medium text-foreground mb-3 font-display">My Workspaces</h2>
          <div className="grid gap-3 sm:grid-cols-2">
            {myWorkspaces.map((ws) => (
              <WorkspaceCard key={ws.id} workspace={ws} isMember />
            ))}
          </div>
        </section>
      )}

      {(() => {
        const filtered = publicWorkspaces.filter((w) => !myWsIds.has(w.id));
        return (
          <section>
            <h2 className="text-lg font-medium text-foreground mb-3 font-display">Public Workspaces</h2>
            {filtered.length === 0 ? (
              <p className="text-muted text-sm">
                No public workspaces yet.{" "}
                <a href="/rooms" className="text-brand hover:underline">
                  Create one!
                </a>
              </p>
            ) : (
              <div className="grid gap-3 sm:grid-cols-2">
                {filtered.map((ws) => (
                  <WorkspaceCard key={ws.id} workspace={ws} isMember={false} />
                ))}
              </div>
            )}
          </section>
        );
      })()}
    </main>
  );
}

export default function Home() {
  const { user, loading, logout } = useAuth();

  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center text-muted">
        Loading...
      </div>
    );
  }

  return (
    <div className="min-h-screen flex flex-col">
      <Header user={user} onLogout={logout} />
      {user ? <LoggedInHome user={user} /> : <LandingPage />}
    </div>
  );
}
