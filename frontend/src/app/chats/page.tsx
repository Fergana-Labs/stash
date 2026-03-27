"use client";

import { useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import AppShell from "../../components/AppShell";
import NewDMDialog from "../../components/NewDMDialog";
import { useAuth } from "../../hooks/useAuth";
import {
  createPersonalRoom,
  deletePersonalRoom,
  listDMs,
  listPersonalRooms,
} from "../../lib/api";
import { Chat, DMConversation } from "../../lib/types";

export default function ChatsPage() {
  const router = useRouter();
  const { user, loading, logout } = useAuth();
  const [dms, setDMs] = useState<DMConversation[]>([]);
  const [rooms, setRooms] = useState<Chat[]>([]);
  const [showNewDM, setShowNewDM] = useState(false);
  const [showCreateRoom, setShowCreateRoom] = useState(false);
  const [newRoomName, setNewRoomName] = useState("");
  const [newRoomDesc, setNewRoomDesc] = useState("");
  const [error, setError] = useState("");

  const loadData = useCallback(() => {
    if (!user) return;
    Promise.all([
      listDMs().then((r) => r?.dms ?? []).catch(() => [] as DMConversation[]),
      listPersonalRooms().then((r) => r?.chats ?? []).catch(() => [] as Chat[]),
    ]).then(([dmList, roomList]) => {
      setDMs(dmList ?? []);
      setRooms(roomList ?? []);
    });
  }, [user]);

  useEffect(() => {
    if (!loading && user) loadData();
  }, [loading, user, loadData]);

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

  if (loading) {
    return <div className="min-h-screen flex items-center justify-center text-muted">Loading...</div>;
  }
  if (!user) { router.push("/login"); return null; }

  return (
    <AppShell user={user} onLogout={logout}>
      <div className="max-w-3xl mx-auto w-full px-4 py-8">
        <div className="flex items-center justify-between mb-6">
          <h1 className="text-2xl font-bold text-foreground font-display">Chats</h1>
          <div className="flex gap-2">
            <button
              onClick={() => setShowNewDM(true)}
              className="text-sm bg-raised text-dim px-3 py-1.5 rounded border border-border hover:text-foreground"
            >
              New DM
            </button>
            <button
              onClick={() => setShowCreateRoom(true)}
              className="text-sm bg-brand hover:bg-brand-hover text-foreground px-3 py-1.5 rounded"
            >
              New Room
            </button>
          </div>
        </div>

        {error && <p className="text-red-400 text-sm mb-4">{error}</p>}

        {showCreateRoom && (
          <div className="bg-surface border border-border rounded-lg p-4 mb-6">
            <h3 className="text-foreground font-medium mb-3">New Room</h3>
            <input value={newRoomName} onChange={(e) => setNewRoomName(e.target.value)} placeholder="Room name" className="w-full bg-raised border border-border rounded px-3 py-2 text-foreground text-sm mb-2" />
            <input value={newRoomDesc} onChange={(e) => setNewRoomDesc(e.target.value)} placeholder="Description (optional)" className="w-full bg-raised border border-border rounded px-3 py-2 text-foreground text-sm mb-2" />
            <div className="flex gap-2">
              <button onClick={handleCreateRoom} className="bg-brand hover:bg-brand-hover text-foreground px-4 py-1.5 rounded text-sm">Create</button>
              <button onClick={() => setShowCreateRoom(false)} className="bg-raised text-dim px-4 py-1.5 rounded text-sm">Cancel</button>
            </div>
          </div>
        )}

        <NewDMDialog open={showNewDM} onClose={() => { setShowNewDM(false); loadData(); }} />

        {rooms.length > 0 && (
          <section className="mb-8">
            <h2 className="text-sm font-medium text-muted uppercase tracking-wider mb-2">Rooms</h2>
            <div className="space-y-0.5">
              {rooms.map((room) => (
                <div key={room.id} className="flex items-center justify-between px-3 py-2.5 rounded-lg hover:bg-raised transition-colors">
                  <a href={`/rooms/${room.id}`} className="flex items-center gap-3 flex-1 min-w-0">
                    <div className="w-7 h-7 rounded-md bg-brand/15 text-brand flex items-center justify-center text-xs font-bold flex-shrink-0">#</div>
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

        <section>
          <h2 className="text-sm font-medium text-muted uppercase tracking-wider mb-2">Direct Messages</h2>
          {dms.length === 0 ? (
            <p className="text-muted text-sm px-3">No conversations yet.</p>
          ) : (
            <div className="space-y-0.5">
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
                      className={`w-7 h-7 rounded-full flex items-center justify-center text-xs font-bold flex-shrink-0 ${
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
      </div>
    </AppShell>
  );
}
