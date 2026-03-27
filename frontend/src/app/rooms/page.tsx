"use client";

import { useRouter } from "next/navigation";
import { useCallback, useEffect, useMemo, useState } from "react";
import Header from "../../components/Header";
import NewDMDialog from "../../components/NewDMDialog";
import WorkspaceCard from "../../components/RoomCard";
import { useAuth } from "../../hooks/useAuth";
import { createWorkspace, listDMs, listMyWorkspaces, listPublicWorkspaces, joinWorkspace } from "../../lib/api";
import { DMConversation, Workspace } from "../../lib/types";

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
  const [dms, setDMs] = useState<DMConversation[]>([]);
  const [showNewDM, setShowNewDM] = useState(false);
  const myWsIds = useMemo(() => new Set(myWorkspaces.map((w) => w.id)), [myWorkspaces]);

  const loadData = useCallback(() => {
    if (!user) return;
    Promise.all([
      listPublicWorkspaces().then((r) => r.workspaces).catch(() => [] as Workspace[]),
      listMyWorkspaces().then((r) => r.workspaces).catch(() => [] as Workspace[]),
      listDMs().then((r) => r.dms).catch(() => [] as DMConversation[]),
    ]).then(([pub, mine, dmList]) => {
      setPublicWorkspaces(pub);
      setMyWorkspaces(mine);
      setDMs(dmList);
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
    return <div className="min-h-screen flex items-center justify-center text-gray-500">Loading...</div>;
  }
  if (!user) { router.push("/login"); return null; }

  return (
    <div className="min-h-screen flex flex-col">
      <Header user={user} onLogout={logout} />
      <main className="flex-1 max-w-4xl mx-auto w-full px-4 py-8">
        <div className="flex items-center justify-between mb-6">
          <h1 className="text-2xl font-bold text-white">Workspaces</h1>
          <div className="flex gap-2">
            <button onClick={() => setShowNewDM(true)} className="text-sm bg-gray-800 hover:bg-gray-700 text-gray-300 px-3 py-1.5 rounded border border-gray-700">New DM</button>
            <button onClick={() => setShowCreate(true)} className="text-sm bg-blue-600 hover:bg-blue-500 text-white px-3 py-1.5 rounded">Create Workspace</button>
          </div>
        </div>
        {error && <p className="text-red-400 text-sm mb-4">{error}</p>}
        {showCreate && (
          <div className="bg-gray-900 border border-gray-700 rounded-lg p-4 mb-6">
            <h3 className="text-white font-medium mb-3">New Workspace</h3>
            <input value={newName} onChange={(e) => setNewName(e.target.value)} placeholder="Name" className="w-full bg-gray-800 border border-gray-700 rounded px-3 py-2 text-white text-sm mb-2" />
            <input value={newDesc} onChange={(e) => setNewDesc(e.target.value)} placeholder="Description (optional)" className="w-full bg-gray-800 border border-gray-700 rounded px-3 py-2 text-white text-sm mb-2" />
            <label className="flex items-center gap-2 text-sm text-gray-400 mb-3"><input type="checkbox" checked={isPublic} onChange={(e) => setIsPublic(e.target.checked)} /> Public</label>
            <div className="flex gap-2">
              <button onClick={handleCreate} className="bg-blue-600 hover:bg-blue-500 text-white px-4 py-1.5 rounded text-sm">Create</button>
              <button onClick={() => setShowCreate(false)} className="bg-gray-700 hover:bg-gray-600 text-gray-300 px-4 py-1.5 rounded text-sm">Cancel</button>
            </div>
          </div>
        )}
        <div className="bg-gray-900 border border-gray-700 rounded-lg p-4 mb-6">
          <h3 className="text-white font-medium mb-2">Join by Invite Code</h3>
          <div className="flex gap-2">
            <input value={joinCode} onChange={(e) => setJoinCode(e.target.value)} placeholder="Enter invite code" className="flex-1 bg-gray-800 border border-gray-700 rounded px-3 py-2 text-white text-sm" />
            <button onClick={handleJoin} className="bg-green-700 hover:bg-green-600 text-white px-4 py-1.5 rounded text-sm">Join</button>
          </div>
        </div>
        <NewDMDialog open={showNewDM} onClose={() => { setShowNewDM(false); loadData(); }} />
        {myWorkspaces.length > 0 && (
          <section className="mb-8">
            <h2 className="text-lg font-medium text-white mb-3">My Workspaces</h2>
            <div className="grid gap-3 sm:grid-cols-2">{myWorkspaces.map((ws) => <WorkspaceCard key={ws.id} workspace={ws} isMember />)}</div>
          </section>
        )}
        {(() => {
          const filtered = publicWorkspaces.filter((w) => !myWsIds.has(w.id));
          if (filtered.length === 0) return null;
          return (
            <section>
              <h2 className="text-lg font-medium text-white mb-3">Public Workspaces</h2>
              <div className="grid gap-3 sm:grid-cols-2">{filtered.map((ws) => <WorkspaceCard key={ws.id} workspace={ws} isMember={false} />)}</div>
            </section>
          );
        })()}
      </main>
    </div>
  );
}
