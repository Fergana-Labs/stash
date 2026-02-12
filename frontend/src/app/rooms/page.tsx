"use client";

import { useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import Header from "../../components/Header";
import RoomCard from "../../components/RoomCard";
import { useAuth } from "../../hooks/useAuth";
import { createRoom, listMyRooms, listPublicRooms } from "../../lib/api";
import { Room } from "../../lib/types";

export default function RoomsPage() {
  const router = useRouter();
  const { user, loading, logout } = useAuth();
  const [publicRooms, setPublicRooms] = useState<Room[]>([]);
  const [myRooms, setMyRooms] = useState<Room[]>([]);
  const [showCreate, setShowCreate] = useState(false);
  const [newRoomName, setNewRoomName] = useState("");
  const [newRoomDesc, setNewRoomDesc] = useState("");
  const [joinCode, setJoinCode] = useState("");
  const [error, setError] = useState("");
  const myRoomIds = new Set(myRooms.map((r) => r.id));

  const loadRooms = useCallback(async () => {
    listPublicRooms().then((r) => setPublicRooms(r.rooms)).catch(() => {});
    if (user) {
      listMyRooms().then((r) => setMyRooms(r.rooms)).catch(() => {});
    }
  }, [user]);

  useEffect(() => {
    loadRooms();
  }, [loadRooms]);

  const handleCreate = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");
    try {
      const room = await createRoom(newRoomName, newRoomDesc);
      setShowCreate(false);
      setNewRoomName("");
      setNewRoomDesc("");
      router.push(`/rooms/${room.id}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to create room");
    }
  };

  const handleJoin = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");
    try {
      const { joinRoom } = await import("../../lib/api");
      const room = await joinRoom(joinCode.trim());
      router.push(`/rooms/${room.id}`);
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
              Create Room
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
            <input
              type="text"
              value={newRoomName}
              onChange={(e) => setNewRoomName(e.target.value)}
              required
              placeholder="Room name"
              className="w-full bg-gray-900 border border-gray-700 rounded px-3 py-2 text-sm text-white focus:outline-none focus:border-blue-500"
            />
            <input
              type="text"
              value={newRoomDesc}
              onChange={(e) => setNewRoomDesc(e.target.value)}
              placeholder="Description (optional)"
              className="w-full bg-gray-900 border border-gray-700 rounded px-3 py-2 text-sm text-white focus:outline-none focus:border-blue-500"
            />
            <div className="flex gap-2">
              <button
                type="submit"
                className="bg-blue-600 hover:bg-blue-500 text-white px-4 py-2 rounded text-sm"
              >
                Create
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

        {user && myRooms.length > 0 && (
          <section className="mb-8">
            <h2 className="text-lg font-medium text-white mb-3">My Rooms</h2>
            <div className="grid gap-3 sm:grid-cols-2">
              {myRooms.map((room) => (
                <RoomCard key={room.id} room={room} isMember />
              ))}
            </div>
          </section>
        )}

        <section>
          <h2 className="text-lg font-medium text-white mb-3">Public Rooms</h2>
          {publicRooms.length === 0 ? (
            <p className="text-gray-500 text-sm">No public rooms yet.</p>
          ) : (
            <div className="grid gap-3 sm:grid-cols-2">
              {publicRooms.map((room) => (
                <RoomCard
                  key={room.id}
                  room={room}
                  isMember={myRoomIds.has(room.id)}
                />
              ))}
            </div>
          )}
        </section>
      </main>
    </div>
  );
}
