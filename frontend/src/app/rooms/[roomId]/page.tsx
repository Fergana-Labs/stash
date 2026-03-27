"use client";

import { useParams, useRouter } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";
import Header from "../../../components/Header";
import ChatInput from "../../../components/ChatInput";
import MessageList from "../../../components/MessageList";
import { useAuth } from "../../../hooks/useAuth";
import {
  getPersonalRoom,
  getPersonalRoomMessages,
  sendPersonalRoomMessage,
  deletePersonalRoom,
} from "../../../lib/api";
import { Chat, Message, WSEvent } from "../../../lib/types";

export default function PersonalRoomPage() {
  const params = useParams();
  const router = useRouter();
  const chatId = params.roomId as string;
  const { user, loading, logout } = useAuth();

  const [room, setRoom] = useState<Chat | null>(null);
  const [messages, setMessages] = useState<Message[]>([]);
  const [typingUser, setTypingUser] = useState<string | null>(null);
  const [searchQuery, setSearchQuery] = useState("");
  const [isSearching] = useState(false);
  const [error, setError] = useState("");
  const wsRef = useRef<WebSocket | null>(null);

  const loadRoom = useCallback(async () => {
    try {
      const r = await getPersonalRoom(chatId);
      setRoom(r);
    } catch {
      setError("Room not found");
    }
  }, [chatId]);

  const loadMessages = useCallback(async () => {
    try {
      const res = await getPersonalRoomMessages(chatId);
      setMessages(res.messages);
    } catch {
      // ignore
    }
  }, [chatId]);

  useEffect(() => {
    if (user) {
      loadRoom();
      loadMessages();
    }
  }, [user, loadRoom, loadMessages]);

  // WebSocket connection
  useEffect(() => {
    if (!user) return;
    const token = localStorage.getItem("moltchat_token");
    if (!token) return;

    const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
    const wsUrl = `${protocol}//${window.location.host}/api/v1/rooms/${chatId}/ws?token=${token}`;
    const ws = new WebSocket(wsUrl);
    wsRef.current = ws;

    ws.onmessage = (event) => {
      try {
        const data: WSEvent = JSON.parse(event.data);
        if (data.type === "message" && data.id) {
          setMessages((prev) => [
            ...prev,
            {
              id: data.id!,
              chat_id: data.chat_id || chatId,
              sender_id: data.sender_id || "",
              sender_name: data.sender_name || "",
              sender_display_name: data.sender_display_name || null,
              sender_type: (data.sender_type as "human" | "agent") || "human",
              content: data.content || "",
              message_type: (data.message_type as "text" | "system") || "text",
              reply_to_id: data.reply_to_id || null,
              created_at: data.created_at || new Date().toISOString(),
            },
          ]);
        } else if (data.type === "typing" && data.user) {
          setTypingUser(data.user);
          setTimeout(() => setTypingUser(null), 3000);
        }
      } catch {
        // ignore
      }
    };

    return () => {
      ws.close();
      wsRef.current = null;
    };
  }, [user, chatId]);

  const handleSend = useCallback(
    async (content: string) => {
      try {
        await sendPersonalRoomMessage(chatId, content);
      } catch (err) {
        setError(err instanceof Error ? err.message : "Failed to send message");
      }
    },
    [chatId]
  );

  const handleDelete = async () => {
    if (!confirm("Delete this room?")) return;
    try {
      await deletePersonalRoom(chatId);
      router.push("/rooms");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to delete room");
    }
  };

  if (loading) {
    return <div className="min-h-screen flex items-center justify-center text-muted">Loading...</div>;
  }
  if (!user) { router.push("/login"); return null; }

  return (
    <div className="h-screen flex flex-col">
      <Header user={user} onLogout={logout} />
      <div className="bg-surface border-b border-border px-4 py-2 flex items-center justify-between">
        <div className="flex items-center gap-3">
          <a href="/rooms" className="text-dim hover:text-foreground text-sm">&larr; Rooms</a>
          <h1 className="text-foreground font-medium">{room?.name || "Loading..."}</h1>
          {room?.description && (
            <span className="text-muted text-sm hidden sm:inline">{room.description}</span>
          )}
        </div>
        <button
          onClick={handleDelete}
          className="text-xs text-red-400 hover:text-red-300 px-2 py-1"
        >
          Delete
        </button>
      </div>
      {error && (
        <div className="bg-red-900/30 border-b border-red-800 text-red-400 text-sm px-4 py-2">
          {error}
          <button onClick={() => setError("")} className="ml-2 text-red-500 hover:text-red-300">&times;</button>
        </div>
      )}
      <MessageList
        messages={messages}
        currentUserId={user.id}
        typingUser={typingUser}
        searchQuery={searchQuery}
        onSearchChange={setSearchQuery}
        isSearching={isSearching}
      />
      <div className="p-4 border-t border-border bg-surface">
        <ChatInput onSend={handleSend} />
      </div>
    </div>
  );
}
