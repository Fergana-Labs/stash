"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import AppShell from "../../components/AppShell";
import NewDMDialog from "../../components/NewDMDialog";
import { useAuth } from "../../hooks/useAuth";
import { listAllChats, listChats, createPersonalRoom } from "../../lib/api";
import { Chat, ChatWithWorkspace, DMWithUser } from "../../lib/types";

function buildChatHref(item: {
  id: string;
  kind: "workspace" | "room" | "dm";
  workspaceId?: string | null;
  label?: string;
}) {
  const params = new URLSearchParams({ kind: item.kind });
  if (item.workspaceId) params.set("workspaceId", item.workspaceId);
  if (item.label) params.set("label", item.label);
  return `/chats/${item.id}?${params.toString()}`;
}

export default function ChatsPage() {
  const router = useRouter();
  const wsId = typeof window !== "undefined" ? new URLSearchParams(window.location.search).get("ws") : null;
  const { user, loading, logout } = useAuth();
  const [chats, setChats] = useState<ChatWithWorkspace[]>([]);
  const [dms, setDMs] = useState<DMWithUser[]>([]);
  const [showNewDM, setShowNewDM] = useState(false);
  const [showCreateRoom, setShowCreateRoom] = useState(false);
  const [newRoomName, setNewRoomName] = useState("");
  const [newRoomDesc, setNewRoomDesc] = useState("");
  const [error, setError] = useState("");

  const loadData = useCallback(async () => {
    try {
      if (wsId) {
        const res = await listChats(wsId);
        const c = (res?.chats ?? []).map((c: any) => ({ ...c, workspace_id: wsId, workspace_name: "" }));
        setChats(c);
        setDMs([]);
      } else {
        const res = await listAllChats();
        setChats(res?.chats ?? []);
        setDMs(res?.dms ?? []);
      }
    } catch {
      // ignore
    }
  }, [wsId]);

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
            <button onClick={() => setShowNewDM(true)} className="text-sm bg-raised text-dim px-3 py-1.5 rounded border border-border hover:text-foreground">New DM</button>
            <button onClick={() => setShowCreateRoom(true)} className="text-sm bg-brand hover:bg-brand-hover text-foreground px-3 py-1.5 rounded">New Room</button>
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

        {chats.length > 0 && (
          <section className="mb-8">
            <h2 className="text-sm font-medium text-muted uppercase tracking-wider mb-2">Rooms</h2>
            <div className="space-y-0.5">
              {chats.map((chat) => (
                <Link
                  key={chat.id}
                  href={buildChatHref({
                    id: chat.id,
                    kind: chat.workspace_id ? "workspace" : "room",
                    workspaceId: chat.workspace_id,
                    label: chat.name,
                  })}
                  className="flex items-center gap-3 px-3 py-2.5 rounded-lg hover:bg-raised transition-colors"
                >
                  <div className="w-7 h-7 rounded-md bg-brand/15 text-brand flex items-center justify-center text-xs font-bold flex-shrink-0">#</div>
                  <div className="min-w-0 flex-1">
                    <div className="text-sm text-foreground truncate">{chat.name}</div>
                    {chat.description && <div className="text-xs text-muted truncate">{chat.description}</div>}
                  </div>
                  {chat.workspace_name && (
                    <span className="text-[10px] text-muted bg-raised px-1.5 py-0.5 rounded flex-shrink-0">
                      {chat.workspace_name}
                    </span>
                  )}
                </Link>
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
                  <Link
                    key={dm.id}
                    href={buildChatHref({
                      id: dm.id,
                      kind: "dm",
                      label: displayName,
                    })}
                    className="flex items-center gap-3 px-3 py-2.5 rounded-lg hover:bg-raised transition-colors"
                  >
                    <div className={`w-7 h-7 rounded-full flex items-center justify-center text-xs font-bold flex-shrink-0 ${other?.type === "persona" ? "bg-agent-muted text-agent" : "bg-human-muted text-human"}`}>
                      {displayName.charAt(0).toUpperCase()}
                    </div>
                    <div className="min-w-0 flex-1">
                      <div className="text-sm text-foreground truncate">{displayName}</div>
                      <div className="text-xs text-muted">@{other?.name || "unknown"}</div>
                    </div>
                    {dm.updated_at && (
                      <div className="text-xs text-muted flex-shrink-0">
                        {new Date(dm.updated_at).toLocaleDateString()}
                      </div>
                    )}
                  </Link>
                );
              })}
            </div>
          )}
        </section>
      </div>
    </AppShell>
  );
}
