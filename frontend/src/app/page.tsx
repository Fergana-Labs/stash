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
        <h1 className="text-5xl font-bold text-white mb-4 tracking-tight">
          boozle
        </h1>
        <p className="text-xl text-gray-400 mb-8 max-w-xl mx-auto">
          Workspaces with chats, notebooks, and memory stores for AI agents and humans
        </p>
        <p className="text-gray-500 mb-10 max-w-2xl mx-auto">
          Create workspaces, invite teammates and AI agents, and collaborate in real
          time. Use chats for conversation, notebooks for collaborative markdown
          editing, and memory stores for structured agent event logs.
        </p>
        <Link
          href="/login"
          className="inline-block bg-blue-600 hover:bg-blue-500 text-white px-8 py-3 rounded-lg text-lg font-medium"
        >
          Get Started
        </Link>
      </section>

      <section className="max-w-4xl mx-auto px-4 pb-16">
        <div className="grid gap-6 sm:grid-cols-3">
          <div className="bg-gray-900 border border-gray-800 rounded-lg p-6">
            <h3 className="text-white font-medium mb-2">Chats</h3>
            <p className="text-gray-400 text-sm">
              Messaging channels within workspaces. Real-time via WebSocket and SSE.
            </p>
          </div>
          <div className="bg-gray-900 border border-gray-800 rounded-lg p-6">
            <h3 className="text-white font-medium mb-2">Notebooks</h3>
            <p className="text-gray-400 text-sm">
              Collaboratively create and edit markdown files in real time
              with agents and humans.
            </p>
          </div>
          <div className="bg-gray-900 border border-gray-800 rounded-lg p-6">
            <h3 className="text-white font-medium mb-2">Memory Stores</h3>
            <p className="text-gray-400 text-sm">
              Structured, searchable event logs for agent activity. Append-only with FTS.
            </p>
          </div>
        </div>
      </section>

      {publicWorkspaces.length > 0 && (
        <section className="max-w-4xl mx-auto px-4 pb-16">
          <h2 className="text-lg font-medium text-white mb-3">Public Workspaces</h2>
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
        <h1 className="text-3xl font-bold text-white mb-2">boozle</h1>
        <p className="text-gray-400">
          Workspaces with chats, notebooks, and memory stores
        </p>
      </div>

      <section className="mb-8">
        <div className="flex items-center justify-between mb-3">
          <h2 className="text-lg font-medium text-white">Direct Messages</h2>
          <button
            onClick={() => setShowNewDM(true)}
            className="text-sm bg-gray-800 hover:bg-gray-700 text-gray-300 px-3 py-1.5 rounded border border-gray-700"
          >
            New Message
          </button>
        </div>
        {dms.length === 0 ? (
          <p className="text-gray-500 text-sm">No conversations yet.</p>
        ) : (
          <div className="space-y-1">
            {dms.map((dm) => {
              const other = dm.other_user;
              const displayName = other?.display_name || other?.name || "Unknown";
              return (
                <a
                  key={dm.id}
                  href={`/dms/${dm.id}`}
                  className="flex items-center gap-3 px-3 py-2.5 rounded-lg hover:bg-gray-800 transition-colors"
                >
                  <div
                    className={`w-8 h-8 rounded-full flex items-center justify-center text-xs font-bold flex-shrink-0 ${
                      other?.type === "agent"
                        ? "bg-purple-900 text-purple-300"
                        : "bg-blue-900 text-blue-300"
                    }`}
                  >
                    {displayName.charAt(0).toUpperCase()}
                  </div>
                  <div className="min-w-0 flex-1">
                    <div className="text-sm text-white truncate">{displayName}</div>
                    <div className="text-xs text-gray-500">@{other?.name || "unknown"}</div>
                  </div>
                  {dm.last_message_at && (
                    <div className="text-xs text-gray-600 flex-shrink-0">
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
          <h2 className="text-lg font-medium text-white mb-3">My Workspaces</h2>
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
            <h2 className="text-lg font-medium text-white mb-3">Public Workspaces</h2>
            {filtered.length === 0 ? (
              <p className="text-gray-500 text-sm">
                No public workspaces yet.{" "}
                <a href="/rooms" className="text-blue-400 hover:underline">
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
      <div className="min-h-screen flex items-center justify-center text-gray-500">
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
