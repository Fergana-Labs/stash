"use client";

import { useParams, useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import Header from "../../../components/Header";
import { useAuth } from "../../../hooks/useAuth";
import { joinRoom } from "../../../lib/api";

export default function JoinPage() {
  const params = useParams();
  const router = useRouter();
  const code = params.code as string;
  const { user, loading, logout } = useAuth();
  const [status, setStatus] = useState<"idle" | "joining" | "error">("idle");
  const [error, setError] = useState("");

  useEffect(() => {
    if (loading) return;
    if (!user) return;
    if (status !== "idle") return;

    setStatus("joining");
    joinRoom(code)
      .then((room) => {
        router.push(`/rooms/${room.id}`);
      })
      .catch((err) => {
        setStatus("error");
        setError(err instanceof Error ? err.message : "Failed to join room");
      });
  }, [code, user, loading, status, router]);

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
      <main className="flex-1 flex items-center justify-center px-4">
        <div className="text-center">
          {!user ? (
            <div>
              <p className="text-gray-400 mb-4">
                You need to be logged in to join a room.
              </p>
              <a
                href="/login"
                className="bg-blue-600 hover:bg-blue-500 text-white px-4 py-2 rounded text-sm"
              >
                Register / Login
              </a>
            </div>
          ) : status === "joining" ? (
            <p className="text-gray-400">Joining room...</p>
          ) : status === "error" ? (
            <div>
              <p className="text-red-400 mb-4">{error}</p>
              <button
                onClick={() => router.push("/rooms")}
                className="bg-gray-700 hover:bg-gray-600 text-white px-4 py-2 rounded text-sm"
              >
                Go to Rooms
              </button>
            </div>
          ) : null}
        </div>
      </main>
    </div>
  );
}
