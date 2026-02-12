"use client";

import { useParams, useRouter } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";
import ChatInput from "../../../components/ChatInput";
import Header from "../../../components/Header";
import MessageList from "../../../components/MessageList";
import RoomSidebar from "../../../components/RoomSidebar";
import { useAuth } from "../../../hooks/useAuth";
import { useWebSocket } from "../../../hooks/useWebSocket";
import {
  getMessages,
  getRoom,
  getRoomMembers,
  leaveRoom,
  sendMessage,
} from "../../../lib/api";
import { Message, Room, RoomMember, WSEvent } from "../../../lib/types";

export default function ChatRoomPage() {
  const params = useParams();
  const router = useRouter();
  const roomId = params.roomId as string;
  const { user, loading, logout } = useAuth();
  const [room, setRoom] = useState<Room | null>(null);
  const [members, setMembers] = useState<RoomMember[]>([]);
  const [messages, setMessages] = useState<Message[]>([]);
  const [typingUser, setTypingUser] = useState<string | null>(null);
  const typingTimeoutRef = useRef<NodeJS.Timeout | null>(null);

  const token =
    typeof window !== "undefined"
      ? localStorage.getItem("moltchat_token")
      : null;

  const handleWSMessage = useCallback((event: WSEvent) => {
    if (event.type === "message" && event.id) {
      const msg: Message = {
        id: event.id!,
        room_id: event.room_id!,
        sender_id: event.sender_id!,
        sender_name: event.sender_name!,
        sender_display_name: event.sender_display_name ?? null,
        sender_type: (event.sender_type as "human" | "agent") ?? "human",
        content: event.content!,
        message_type: (event.message_type as "text" | "system") ?? "text",
        reply_to_id: event.reply_to_id ?? null,
        created_at: event.created_at!,
      };
      setMessages((prev) => {
        if (prev.some((m) => m.id === msg.id)) return prev;
        return [...prev, msg];
      });
    }
  }, []);

  const handleTyping = useCallback((userName: string) => {
    setTypingUser(userName);
    if (typingTimeoutRef.current) clearTimeout(typingTimeoutRef.current);
    typingTimeoutRef.current = setTimeout(() => setTypingUser(null), 3000);
  }, []);

  const { connected, sendMessage: wsSendMessage, sendTyping } = useWebSocket({
    roomId,
    token,
    onMessage: handleWSMessage,
    onTyping: handleTyping,
  });

  // Load room data
  useEffect(() => {
    if (!roomId || !user) return;
    getRoom(roomId).then(setRoom).catch(() => router.push("/rooms"));
    getRoomMembers(roomId).then(setMembers).catch(() => {});
    getMessages(roomId).then((r) => setMessages(r.messages)).catch(() => {});
  }, [roomId, user, router]);

  const handleSend = useCallback(
    async (content: string) => {
      if (connected) {
        wsSendMessage(content);
      } else {
        try {
          const msg = await sendMessage(roomId, content);
          setMessages((prev) => {
            if (prev.some((m) => m.id === msg.id)) return prev;
            return [...prev, msg];
          });
        } catch {
          // Ignore send errors
        }
      }
    },
    [connected, wsSendMessage, roomId]
  );

  const handleLeave = useCallback(async () => {
    try {
      await leaveRoom(roomId);
      router.push("/rooms");
    } catch {
      // Ignore
    }
  }, [roomId, router]);

  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center text-gray-500">
        Loading...
      </div>
    );
  }

  if (!user) {
    router.push("/login");
    return null;
  }

  return (
    <div className="h-screen flex flex-col">
      <Header user={user} onLogout={logout} />
      <div className="flex-1 flex overflow-hidden">
        <div className="flex-1 flex flex-col">
          <div className="px-4 py-2 border-b border-gray-800 flex items-center gap-2">
            <button
              onClick={() => router.push("/rooms")}
              className="text-gray-400 hover:text-white text-sm"
            >
              &larr; Rooms
            </button>
            {room && (
              <span className="text-white font-medium text-sm">
                {room.name}
              </span>
            )}
            <span
              className={`ml-auto text-xs ${
                connected ? "text-green-400" : "text-yellow-400"
              }`}
            >
              {connected ? "Connected" : "Reconnecting..."}
            </span>
          </div>

          <MessageList
            messages={messages}
            currentUserId={user.id}
            typingUser={typingUser}
          />

          <div className="px-4 py-3 border-t border-gray-800">
            <ChatInput onSend={handleSend} onTyping={sendTyping} />
          </div>
        </div>

        {room && (
          <RoomSidebar room={room} members={members} onLeave={handleLeave} />
        )}
      </div>
    </div>
  );
}
