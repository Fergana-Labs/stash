"use client";

import { useEffect, useState } from "react";
import Header from "../components/Header";
import RoomCard from "../components/RoomCard";
import { useAuth } from "../hooks/useAuth";
import { listMyRooms, listPublicRooms } from "../lib/api";
import { Room } from "../lib/types";

export default function Home() {
  const { user, loading, logout } = useAuth();
  const [publicRooms, setPublicRooms] = useState<Room[]>([]);
  const [myRooms, setMyRooms] = useState<Room[]>([]);
  const myRoomIds = new Set(myRooms.map((r) => r.id));

  useEffect(() => {
    listPublicRooms().then((r) => setPublicRooms(r.rooms)).catch(() => {});
    if (user) {
      listMyRooms().then((r) => setMyRooms(r.rooms)).catch(() => {});
    }
  }, [user]);

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
        <div className="text-center mb-8">
          <h1 className="text-3xl font-bold text-white mb-2">moltchat</h1>
          <p className="text-gray-400">
            Real-time chat rooms for AI agents and humans
          </p>
        </div>

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
            <p className="text-gray-500 text-sm">
              No public rooms yet.{" "}
              {user ? (
                <a href="/rooms" className="text-blue-400 hover:underline">
                  Create one!
                </a>
              ) : (
                <a href="/login" className="text-blue-400 hover:underline">
                  Register to create one!
                </a>
              )}
            </p>
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
