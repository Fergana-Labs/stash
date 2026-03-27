"use client";

import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import AppShell from "../../../components/AppShell";
import WorkspaceSidebar from "../../../components/workspace/WorkspaceSidebar";
import { useAuth } from "../../../hooks/useAuth";
import {
  createNotebook,
  deleteNotebook,
  getWorkspace,
  listNotebooks,
  listChats,
  joinWorkspace as apiJoinRoom,
  getWorkspaceMembers,
  leaveWorkspace,
  deleteWorkspace,
  kickWorkspaceMember,
  updateWorkspace,
} from "../../../lib/api";
import { Chat, Notebook, Workspace, WorkspaceMember } from "../../../lib/types";

export default function WorkspacePage() {
  const params = useParams();
  const router = useRouter();
  const workspaceId = params.workspaceId as string;
  const { user, loading, logout } = useAuth();

  const [workspace, setWorkspace] = useState<Workspace | null>(null);
  const [notebooks, setNotebooks] = useState<Notebook[]>([]);
  const [chats, setChats] = useState<Chat[]>([]);
  const [members, setMembers] = useState<WorkspaceMember[]>([]);
  const [isMember, setIsMember] = useState(false);
  const [error, setError] = useState("");
  const [showManageSidebar, setShowManageSidebar] = useState(false);

  const loadWorkspace = useCallback(async () => {
    try { setWorkspace(await getWorkspace(workspaceId)); } catch { setError("Workspace not found"); }
  }, [workspaceId]);

  const loadData = useCallback(async () => {
    try {
      const [nbRes, chatRes, m] = await Promise.all([
        listNotebooks(workspaceId).then(r => r?.notebooks ?? []).catch(() => [] as Notebook[]),
        listChats(workspaceId).then(r => r?.chats ?? []).catch(() => [] as Chat[]),
        getWorkspaceMembers(workspaceId).catch(() => [] as WorkspaceMember[]),
      ]);
      setNotebooks(nbRes);
      setChats(chatRes);
      setMembers(m);
      if (user) setIsMember(m.some(mem => mem.user_id === user.id));
    } catch { setIsMember(false); }
  }, [workspaceId, user]);

  useEffect(() => { loadWorkspace(); }, [loadWorkspace]);
  useEffect(() => { if (user) loadData(); }, [user, loadData]);

  const handleJoin = async () => {
    if (!workspace) return;
    try { await apiJoinRoom(workspace.invite_code); await loadData(); }
    catch (err) { setError(err instanceof Error ? err.message : "Failed to join"); }
  };

  const handleCreateNotebook = async () => {
    const name = prompt("Notebook name:");
    if (!name) return;
    try { await createNotebook(workspaceId, name); await loadData(); }
    catch (err) { setError(err instanceof Error ? err.message : "Failed to create notebook"); }
  };

  const handleDeleteNotebook = async (nbId: string) => {
    if (!confirm("Delete this notebook and all its pages?")) return;
    try { await deleteNotebook(workspaceId, nbId); await loadData(); }
    catch (err) { setError(err instanceof Error ? err.message : "Failed to delete"); }
  };

  const isOwner = members.some(m => m.user_id === user?.id && m.role === "owner");

  if (loading) return <div className="min-h-screen flex items-center justify-center text-muted">Loading...</div>;
  if (!user) { router.push("/login"); return null; }

  return (
    <AppShell user={user} onLogout={logout}>
      <div className="flex flex-col h-full">
        {/* Workspace header */}
        <div className="bg-surface border-b border-border px-4 py-2 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <Link href="/rooms" className="text-dim hover:text-foreground text-sm">&larr;</Link>
            <h1 className="text-foreground font-medium">{workspace?.name || "Loading..."}</h1>
            {workspace?.description && <span className="text-muted text-sm hidden sm:inline">{workspace.description}</span>}
          </div>
          <div className="flex items-center gap-3">
            <span className="text-xs text-muted">{members.length} member{members.length !== 1 ? "s" : ""}</span>
            {isMember && (
              <button onClick={() => setShowManageSidebar(!showManageSidebar)}
                className={`text-xs px-3 py-1 rounded border ${showManageSidebar ? "bg-brand border-brand text-foreground" : "bg-raised border-border text-dim hover:text-foreground"}`}>
                Settings
              </button>
            )}
          </div>
        </div>

        {error && (
          <div className="bg-red-900/30 border-b border-red-800 text-red-400 text-sm px-4 py-2">
            {error}<button onClick={() => setError("")} className="ml-2 text-red-500 hover:text-red-300">&times;</button>
          </div>
        )}

        {!isMember ? (
          <div className="flex-1 flex items-center justify-center">
            <div className="text-center">
              <p className="text-dim mb-4">You&apos;re not a member of this workspace.</p>
              <button onClick={handleJoin} className="bg-brand hover:bg-brand-hover text-foreground px-6 py-2 rounded">Join Workspace</button>
            </div>
          </div>
        ) : (
          <div className="flex-1 flex overflow-hidden">
            <div className="flex-1 overflow-y-auto px-6 py-6 max-w-3xl">
              {/* Chats */}
              <section className="mb-8">
                <div className="flex items-center justify-between mb-3">
                  <h2 className="text-sm font-medium text-muted uppercase tracking-wider">Chats</h2>
                </div>
                {chats.length === 0 ? (
                  <p className="text-muted text-sm">No chats in this workspace yet.</p>
                ) : (
                  <div className="space-y-1">
                    {chats.map(chat => (
                      <div key={chat.id} className="flex items-center gap-3 px-3 py-2 rounded-lg hover:bg-raised transition-colors">
                        <div className="w-7 h-7 rounded-md bg-brand/15 text-brand flex items-center justify-center text-xs font-bold">#</div>
                        <div className="text-sm text-foreground">{chat.name}</div>
                      </div>
                    ))}
                  </div>
                )}
              </section>

              {/* Notebooks */}
              <section className="mb-8">
                <div className="flex items-center justify-between mb-3">
                  <h2 className="text-sm font-medium text-muted uppercase tracking-wider">Notebooks</h2>
                  <button onClick={handleCreateNotebook} className="text-xs text-brand hover:text-brand-hover">+ New</button>
                </div>
                {notebooks.length === 0 ? (
                  <p className="text-muted text-sm">No notebooks yet.</p>
                ) : (
                  <div className="space-y-1">
                    {notebooks.map(nb => (
                      <div key={nb.id} className="flex items-center justify-between px-3 py-2 rounded-lg hover:bg-raised transition-colors">
                        <Link href="/notebooks" className="flex items-center gap-3 flex-1 min-w-0">
                          <div className="w-7 h-7 rounded-md bg-green-500/15 text-green-500 flex items-center justify-center text-xs font-bold">N</div>
                          <div>
                            <div className="text-sm text-foreground">{nb.name}</div>
                            {nb.description && <div className="text-xs text-muted">{nb.description}</div>}
                          </div>
                        </Link>
                        <button onClick={() => handleDeleteNotebook(nb.id)} className="text-xs text-red-400 hover:text-red-300 px-2 py-1">Delete</button>
                      </div>
                    ))}
                  </div>
                )}
              </section>
            </div>

            {/* Settings sidebar */}
            {showManageSidebar && workspace && user && (
              <WorkspaceSidebar
                workspace={workspace}
                members={members}
                currentUserId={user.id}
                isOwner={isOwner}
                onLeave={async () => { await leaveWorkspace(workspaceId); router.push("/rooms"); }}
                onDelete={async () => { await deleteWorkspace(workspaceId); router.push("/rooms"); }}
                onKickMember={async (uid) => { await kickWorkspaceMember(workspaceId, uid); await loadData(); }}
                onUpdateWorkspace={async (data) => { setWorkspace(await updateWorkspace(workspaceId, data)); }}
              />
            )}
          </div>
        )}
      </div>
    </AppShell>
  );
}
