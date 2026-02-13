"use client";

import { useRouter } from "next/navigation";
import { useCallback, useEffect, useMemo, useState } from "react";
import Header from "../../components/Header";
import NewDMDialog from "../../components/NewDMDialog";
import RoomCard from "../../components/RoomCard";
import { useAuth } from "../../hooks/useAuth";
import { createRoom, listDMs, listMyRooms, listPublicRooms } from "../../lib/api";
import { DMConversation, Room } from "../../lib/types";

export default function RoomsPage() {
  const router = useRouter();
  const { user, loading, logout } = useAuth();
  const [publicRooms, setPublicRooms] = useState<Room[]>([]);
  const [myRooms, setMyRooms] = useState<Room[]>([]);
  const [showCreate, setShowCreate] = useState(false);
  const [newRoomName, setNewRoomName] = useState("");
  const [newRoomDesc, setNewRoomDesc] = useState("");
  const [isPublic, setIsPublic] = useState(true);
  const [createType, setCreateType] = useState<"chat" | "workspace">("chat");
  const [joinCode, setJoinCode] = useState("");
  const [error, setError] = useState("");
  const [dms, setDMs] = useState<DMConversation[]>([]);
  const [showNewDM, setShowNewDM] = useState(false);
  const myRoomIds = useMemo(() => new Set(myRooms.map((r) => r.id)), [myRooms]);

  const myChatRooms = myRooms.filter((r) => (r.type || "chat") === "chat");
  const myWorkspaces = myRooms.filter((r) => r.type === "workspace");
  const publicChatRooms = publicRooms.filter((r) => (r.type || "chat") === "chat");
  const publicWorkspaces = publicRooms.filter((r) => r.type === "workspace");

  const loadRooms = useCallback(async () => {
    const publicPromise = listPublicRooms().then((r) => r.rooms).catch(() => [] as Room[]);
    const myPromise = user
      ? listMyRooms().then((r) => r.rooms).catch(() => [] as Room[])
      : Promise.resolve([] as Room[]);
    const dmPromise = user
      ? listDMs().then((r) => r.dms).catch(() => [] as DMConversation[])
      : Promise.resolve([] as DMConversation[]);
    const [pub, mine, dmList] = await Promise.all([publicPromise, myPromise, dmPromise]);
    setPublicRooms(pub);
    setMyRooms(mine);
    setDMs(dmList);
  }, [user]);

  useEffect(() => {
    loadRooms();
  }, [loadRooms]);

  const handleCreate = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");
    try {
      const room = await createRoom(newRoomName, newRoomDesc, isPublic, createType);
      setShowCreate(false);
      setNewRoomName("");
      setNewRoomDesc("");
      setIsPublic(true);
      setCreateType("chat");
      if (room.type === "workspace") {
        router.push(`/workspaces/${room.id}`);
      } else {
        router.push(`/rooms/${room.id}`);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to create");
    }
  };

  const handleJoin = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");
    try {
      const { joinRoom } = await import("../../lib/api");
      const room = await joinRoom(joinCode.trim());
      if (room.type === "workspace") {
        router.push(`/workspaces/${room.id}`);
      } else {
        router.push(`/rooms/${room.id}`);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to join room");
    }
  };

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
      <main className="flex-1 max-w-4xl mx-auto w-full px-4 py-8">
        {error && (
          <div className="bg-red-900/30 border border-red-800 text-red-400 text-sm px-3 py-2 rounded mb-4">
            {error}
          </div>
        )}

        {user && (
          <div className="flex gap-2 mb-6">
            <button
              onClick={() => setShowCreate(!showCreate)}
              className="bg-blue-600 hover:bg-blue-500 text-white px-4 py-2 rounded text-sm"
            >
              Create New
            </button>
            <form onSubmit={handleJoin} className="flex gap-2">
              <input
                type="text"
                value={joinCode}
                onChange={(e) => setJoinCode(e.target.value)}
                placeholder="Invite code..."
                className="bg-gray-800 border border-gray-700 rounded px-3 py-2 text-sm text-white w-36 focus:outline-none focus:border-blue-500"
              />
              <button
                type="submit"
                className="bg-gray-700 hover:bg-gray-600 text-white px-3 py-2 rounded text-sm"
              >
                Join
              </button>
            </form>
          </div>
        )}

        {showCreate && (
          <form
            onSubmit={handleCreate}
            className="bg-gray-800 border border-gray-700 rounded-lg p-4 mb-6 space-y-3"
          >
            <div className="flex gap-2 mb-2">
              <button
                type="button"
                onClick={() => setCreateType("chat")}
                className={`px-3 py-1.5 rounded text-sm ${
                  createType === "chat"
                    ? "bg-blue-600 text-white"
                    : "bg-gray-700 text-gray-300 hover:bg-gray-600"
                }`}
              >
                Chat Room
              </button>
              <button
                type="button"
                onClick={() => setCreateType("workspace")}
                className={`px-3 py-1.5 rounded text-sm ${
                  createType === "workspace"
                    ? "bg-purple-600 text-white"
                    : "bg-gray-700 text-gray-300 hover:bg-gray-600"
                }`}
              >
                Workspace
              </button>
            </div>
            <input
              type="text"
              value={newRoomName}
              onChange={(e) => setNewRoomName(e.target.value)}
              required
              placeholder={createType === "workspace" ? "Workspace name" : "Room name"}
              className="w-full bg-gray-900 border border-gray-700 rounded px-3 py-2 text-sm text-white focus:outline-none focus:border-blue-500"
            />
            <input
              type="text"
              value={newRoomDesc}
              onChange={(e) => setNewRoomDesc(e.target.value)}
              placeholder="Description (optional)"
              className="w-full bg-gray-900 border border-gray-700 rounded px-3 py-2 text-sm text-white focus:outline-none focus:border-blue-500"
            />
            <label className="flex items-center gap-2 text-sm text-gray-300 cursor-pointer">
              <input
                type="checkbox"
                checked={isPublic}
                onChange={(e) => setIsPublic(e.target.checked)}
                className="rounded border-gray-600 bg-gray-800 text-blue-600 focus:ring-blue-500"
              />
              Public
              <span className="text-xs text-gray-500">
                {isPublic
                  ? "(visible to everyone)"
                  : "(invite only)"}
              </span>
            </label>
            <div className="flex gap-2">
              <button
                type="submit"
                className={`${
                  createType === "workspace" ? "bg-purple-600 hover:bg-purple-500" : "bg-blue-600 hover:bg-blue-500"
                } text-white px-4 py-2 rounded text-sm`}
              >
                Create {createType === "workspace" ? "Workspace" : "Room"}
              </button>
              <button
                type="button"
                onClick={() => setShowCreate(false)}
                className="text-gray-400 hover:text-white px-3 py-2 text-sm"
              >
                Cancel
              </button>
            </div>
          </form>
        )}

        {user && (
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
                      href={`/rooms/${dm.id}`}
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
        )}

        <NewDMDialog open={showNewDM} onClose={() => { setShowNewDM(false); loadRooms(); }} />

        {user && myChatRooms.length > 0 && (
          <section className="mb-8">
            <h2 className="text-lg font-medium text-white mb-3">My Rooms</h2>
            <div className="grid gap-3 sm:grid-cols-2">
              {myChatRooms.map((room) => (
                <RoomCard key={room.id} room={room} isMember />
              ))}
            </div>
          </section>
        )}

        {user && myWorkspaces.length > 0 && (
          <section className="mb-8">
            <h2 className="text-lg font-medium text-white mb-3">My Workspaces</h2>
            <div className="grid gap-3 sm:grid-cols-2">
              {myWorkspaces.map((room) => (
                <RoomCard key={room.id} room={room} isMember />
              ))}
            </div>
          </section>
        )}

        <section className="mb-8">
          <h2 className="text-lg font-medium text-white mb-3">Public Rooms</h2>
          {(() => {
            const filtered = publicChatRooms.filter((r) => !myRoomIds.has(r.id));
            return filtered.length === 0 ? (
              <p className="text-gray-500 text-sm">No public rooms yet.</p>
            ) : (
              <div className="grid gap-3 sm:grid-cols-2">
                {filtered.map((room) => (
                  <RoomCard key={room.id} room={room} isMember={false} />
                ))}
              </div>
            );
          })()}
        </section>

        {publicWorkspaces.filter((r) => !myRoomIds.has(r.id)).length > 0 && (
          <section>
            <h2 className="text-lg font-medium text-white mb-3">Public Workspaces</h2>
            <div className="grid gap-3 sm:grid-cols-2">
              {publicWorkspaces
                .filter((r) => !myRoomIds.has(r.id))
                .map((room) => (
                  <RoomCard key={room.id} room={room} isMember={false} />
                ))}
            </div>
          </section>
        )}
      </main>
    </div>
  );
}
