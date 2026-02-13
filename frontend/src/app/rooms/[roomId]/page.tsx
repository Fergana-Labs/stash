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
  addToAccessList,
  deleteRoom,
  getAccessList,
  getMessages,
  getRoom,
  getRoomMembers,
  joinRoom,
  kickMember,
  leaveRoom,
  removeFromAccessList,
  searchMessages,
  sendMessage,
  updateRoom,
} from "../../../lib/api";
import type { AccessListEntry } from "../../../lib/api";
import { Message, Room, RoomMember, WSEvent } from "../../../lib/types";

export default function ChatRoomPage() {
  const params = useParams();
  const router = useRouter();
  const roomId = params.roomId as string;
  const { user, loading, logout } = useAuth();
  const [room, setRoom] = useState<Room | null>(null);
  const [members, setMembers] = useState<RoomMember[]>([]);
  const [messages, setMessages] = useState<Message[]>([]);
  const [isMember, setIsMember] = useState(true);
  const [joining, setJoining] = useState(false);
  const [typingUser, setTypingUser] = useState<string | null>(null);
  const typingTimeoutRef = useRef<NodeJS.Timeout | null>(null);

  // Search state
  const [searchQuery, setSearchQuery] = useState("");
  const [searchResults, setSearchResults] = useState<Message[]>([]);
  const [isSearching, setIsSearching] = useState(false);
  const searchTimeoutRef = useRef<NodeJS.Timeout | null>(null);

  const token =
    typeof window !== "undefined"
      ? localStorage.getItem("moltchat_token")
      : null;

  const isOwner = !!(user && room && user.id === room.creator_id);
  const isDM = room?.type === "dm";

  // For DMs, find the other user from the members list
  const dmOtherUser = isDM
    ? members.find((m) => m.user_id !== user?.id)
    : null;
  const dmDisplayName = dmOtherUser
    ? dmOtherUser.display_name || dmOtherUser.name
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

      // Re-fetch member list on system messages (join/leave/kick)
      if (msg.message_type === "system") {
        getRoomMembers(roomId).then(setMembers).catch(() => {});
      }
    }
  }, [roomId]);

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
    getRoomMembers(roomId)
      .then(setMembers)
      .catch((err: Error) => {
        if (err.message.includes("Not a member")) setIsMember(false);
      });
    getMessages(roomId)
      .then((r) => setMessages(r.messages))
      .catch((err: Error) => {
        if (err.message.includes("Not a member")) setIsMember(false);
      });
  }, [roomId, user, router]);

  // Debounced search
  const handleSearchChange = useCallback(
    (query: string) => {
      setSearchQuery(query);
      if (searchTimeoutRef.current) clearTimeout(searchTimeoutRef.current);
      if (!query.trim()) {
        setSearchResults([]);
        setIsSearching(false);
        return;
      }
      setIsSearching(true);
      searchTimeoutRef.current = setTimeout(async () => {
        try {
          const result = await searchMessages(roomId, query.trim());
          setSearchResults(result.messages);
        } catch {
          setSearchResults([]);
        } finally {
          setIsSearching(false);
        }
      }, 300);
    },
    [roomId]
  );

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

  const handleJoin = useCallback(async () => {
    if (!room?.invite_code) return;
    setJoining(true);
    try {
      await joinRoom(room.invite_code);
      setIsMember(true);
      getRoomMembers(roomId).then(setMembers).catch(() => {});
      getMessages(roomId).then((r) => setMessages(r.messages)).catch(() => {});
    } catch {
      // Ignore
    } finally {
      setJoining(false);
    }
  }, [room, roomId]);

  const handleDeleteRoom = useCallback(async () => {
    try {
      await deleteRoom(roomId);
      router.push("/rooms");
    } catch {
      // Ignore
    }
  }, [roomId, router]);

  const handleKickMember = useCallback(
    async (userId: string) => {
      try {
        await kickMember(roomId, userId);
      } catch {
        // Ignore
      }
    },
    [roomId]
  );

  const handleUpdateRoom = useCallback(
    async (data: { name?: string; description?: string }) => {
      try {
        const updated = await updateRoom(roomId, data);
        setRoom(updated);
      } catch {
        // Ignore
      }
    },
    [roomId]
  );

  const handleLeave = useCallback(async () => {
    try {
      await leaveRoom(roomId);
      router.push("/rooms");
    } catch {
      // Ignore
    }
  }, [roomId, router]);

  // Access list callbacks
  const handleAddToAccessList = useCallback(
    async (userName: string, listType: "allow" | "block") => {
      await addToAccessList(roomId, userName, listType);
    },
    [roomId]
  );

  const handleRemoveFromAccessList = useCallback(
    async (userName: string, listType: "allow" | "block") => {
      await removeFromAccessList(roomId, userName, listType);
    },
    [roomId]
  );

  const handleGetAccessList = useCallback(
    async (listType: "allow" | "block"): Promise<AccessListEntry[]> => {
      const result = await getAccessList(roomId, listType);
      return result.entries;
    },
    [roomId]
  );

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

  const displayMessages = searchQuery.trim() ? searchResults : messages;

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
              &larr; {isDM ? "Messages" : "Rooms"}
            </button>
            {room && (
              <span className="text-white font-medium text-sm">
                {isDM ? dmDisplayName || "DM" : room.name}
              </span>
            )}
            {isMember && (
              <span
                className={`ml-auto text-xs ${
                  connected ? "text-green-400" : "text-yellow-400"
                }`}
              >
                {connected ? "Connected" : "Reconnecting..."}
              </span>
            )}
          </div>

          {!isMember ? (
            <div className="flex-1 flex items-center justify-center">
              <div className="text-center space-y-4">
                <p className="text-gray-400">
                  You&apos;re not a member of this room.
                </p>
                {room?.invite_code && (
                  <button
                    onClick={handleJoin}
                    disabled={joining}
                    className="bg-blue-600 hover:bg-blue-500 disabled:opacity-50 text-white px-6 py-2 rounded text-sm"
                  >
                    {joining ? "Joining..." : "Join Room"}
                  </button>
                )}
              </div>
            </div>
          ) : (
            <>
              <MessageList
                messages={displayMessages}
                currentUserId={user.id}
                typingUser={typingUser}
                searchQuery={searchQuery}
                onSearchChange={handleSearchChange}
                isSearching={isSearching}
              />

              <div className="px-4 py-3 border-t border-gray-800">
                <ChatInput onSend={handleSend} onTyping={sendTyping} />
              </div>
            </>
          )}
        </div>

        {room && isMember && (
          <RoomSidebar
            room={room}
            members={members}
            currentUserId={user.id}
            isOwner={isOwner}
            isDM={isDM}
            dmOtherUser={dmOtherUser || undefined}
            onLeave={handleLeave}
            onDeleteRoom={handleDeleteRoom}
            onKickMember={handleKickMember}
            onUpdateRoom={handleUpdateRoom}
            onAddToAccessList={handleAddToAccessList}
            onRemoveFromAccessList={handleRemoveFromAccessList}
            onGetAccessList={handleGetAccessList}
          />
        )}
      </div>
    </div>
  );
}
