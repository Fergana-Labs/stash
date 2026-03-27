"use client";

import { useRouter } from "next/navigation";
import { useCallback, useEffect, useMemo, useState } from "react";
import AppShell from "../../components/AppShell";
import NewDMDialog from "../../components/NewDMDialog";
import WorkspaceCard from "../../components/RoomCard";
import { useAuth } from "../../hooks/useAuth";
import {
  createWorkspace, createPersonalRoom, listDMs, listMyWorkspaces,
  listPublicWorkspaces, listPersonalRooms, joinWorkspace, deletePersonalRoom,
} from "../../lib/api";
import { Chat, DMConversation, Workspace } from "../../lib/types";

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
  const [personalRooms, setPersonalRooms] = useState<Chat[]>([]);
  const [showNewDM, setShowNewDM] = useState(false);
  const [showCreateRoom, setShowCreateRoom] = useState(false);
  const [newRoomName, setNewRoomName] = useState("");
  const [newRoomDesc, setNewRoomDesc] = useState("");
  const myWsIds = useMemo(() => new Set(myWorkspaces.map((w) => w.id)), [myWorkspaces]);

  const loadData = useCallback(() => {
    if (!user) return;
    Promise.all([
      listPublicWorkspaces().then((r) => r?.workspaces ?? []).catch(() => [] as Workspace[]),
      listMyWorkspaces().then((r) => r?.workspaces ?? []).catch(() => [] as Workspace[]),
      listDMs().then((r) => r?.dms ?? []).catch(() => [] as DMConversation[]),
      listPersonalRooms().then((r) => r?.chats ?? []).catch(() => [] as Chat[]),
    ]).then(([pub, mine, dmList, rooms]) => {
      setPublicWorkspaces(pub ?? []);
      setMyWorkspaces(mine ?? []);
      setDMs(dmList ?? []);
      setPersonalRooms(rooms ?? []);
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

  const handleCreateRoom = async () => {
    if (!newRoomName.trim()) return;
    setError("");
    try {
      const room = await createPersonalRoom(newRoomName.trim(), newRoomDesc.trim());
      setShowCreateRoom(false);
      setNewRoomName("");
      setNewRoomDesc("");
      router.push(`/rooms/${room.id}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to create room");
    }
  };

  const handleDeleteRoom = async (roomId: string) => {
    if (!confirm("Delete this room?")) return;
    try {
      await deletePersonalRoom(roomId);
      loadData();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to delete room");
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
          <h1 className="text-2xl font-bold text-foreground">Workspaces</h1>
          <div className="flex gap-2">
            <button onClick={() => setShowNewDM(true)} className="text-sm bg-raised hover:bg-raised text-dim px-3 py-1.5 rounded border border-border">New DM</button>
            <button onClick={() => setShowCreateRoom(true)} className="text-sm bg-raised hover:bg-raised text-dim px-3 py-1.5 rounded border border-border">New Room</button>
            <button onClick={() => setShowCreate(true)} className="text-sm bg-brand hover:bg-brand-hover text-foreground px-3 py-1.5 rounded">Create Workspace</button>
          </div>
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
              <button onClick={() => setShowCreate(false)} className="bg-raised hover:bg-raised text-dim px-4 py-1.5 rounded text-sm">Cancel</button>
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
        {showCreateRoom && (
          <div className="bg-surface border border-border rounded-lg p-4 mb-6">
            <h3 className="text-foreground font-medium mb-3">New Personal Room</h3>
            <input value={newRoomName} onChange={(e) => setNewRoomName(e.target.value)} placeholder="Room name" className="w-full bg-raised border border-border rounded px-3 py-2 text-foreground text-sm mb-2" />
            <input value={newRoomDesc} onChange={(e) => setNewRoomDesc(e.target.value)} placeholder="Description (optional)" className="w-full bg-raised border border-border rounded px-3 py-2 text-foreground text-sm mb-2" />
            <div className="flex gap-2">
              <button onClick={handleCreateRoom} className="bg-brand hover:bg-brand-hover text-foreground px-4 py-1.5 rounded text-sm">Create</button>
              <button onClick={() => setShowCreateRoom(false)} className="bg-raised text-dim px-4 py-1.5 rounded text-sm">Cancel</button>
            </div>
          </div>
        )}
        <NewDMDialog open={showNewDM} onClose={() => { setShowNewDM(false); loadData(); }} />
        {personalRooms.length > 0 && (
          <section className="mb-8">
            <h2 className="text-lg font-medium text-foreground mb-3">Personal Rooms</h2>
            <div className="space-y-1">
              {personalRooms.map((room) => (
                <div key={room.id} className="flex items-center justify-between px-3 py-2.5 rounded-lg hover:bg-raised transition-colors">
                  <a href={`/rooms/${room.id}`} className="flex items-center gap-3 flex-1 min-w-0">
                    <div className="w-8 h-8 rounded-full bg-brand/20 text-brand flex items-center justify-center text-xs font-bold flex-shrink-0">#</div>
                    <div className="min-w-0">
                      <div className="text-sm text-foreground truncate">{room.name}</div>
                      {room.description && <div className="text-xs text-muted truncate">{room.description}</div>}
                    </div>
                  </a>
                  <button onClick={() => handleDeleteRoom(room.id)} className="text-xs text-red-400 hover:text-red-300 px-2 py-1 flex-shrink-0">Delete</button>
                </div>
              ))}
            </div>
          </section>
        )}
        {myWorkspaces.length > 0 && (
          <section className="mb-8">
            <h2 className="text-lg font-medium text-foreground mb-3">My Workspaces</h2>
            <div className="grid gap-3 sm:grid-cols-2">{myWorkspaces.map((ws) => <WorkspaceCard key={ws.id} workspace={ws} isMember />)}</div>
          </section>
        )}
        {(() => {
          const filtered = publicWorkspaces.filter((w) => !myWsIds.has(w.id));
          if (filtered.length === 0) return null;
          return (
            <section>
              <h2 className="text-lg font-medium text-foreground mb-3">Public Workspaces</h2>
              <div className="grid gap-3 sm:grid-cols-2">{filtered.map((ws) => <WorkspaceCard key={ws.id} workspace={ws} isMember={false} />)}</div>
            </section>
          );
        })()}
      </div>
    </AppShell>
  );
}
