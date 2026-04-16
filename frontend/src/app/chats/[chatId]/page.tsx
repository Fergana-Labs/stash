"use client";

import Link from "next/link";
import { useParams, useRouter, useSearchParams } from "next/navigation";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import AppShell from "../../../components/AppShell";
import ChatInput from "../../../components/ChatInput";
import MessageList from "../../../components/MessageList";
import { useAuth } from "../../../hooks/useAuth";
import {
  fetchWsToken,
  getChat,
  getDMMessages,
  getMessages,
  getPersonalRoom,
  getPersonalRoomMessages,
  sendDMMessage,
  sendMessage,
  sendPersonalRoomMessage,
  getWsBase,
} from "../../../lib/api";
import { Message, WSEvent } from "../../../lib/types";

type ChatKind = "workspace" | "room" | "dm";

export default function ChatThreadPage() {
  const params = useParams();
  const searchParams = useSearchParams();
  const router = useRouter();
  const chatId = params.chatId as string;
  const kind = (searchParams.get("kind") || "room") as ChatKind;
  const workspaceId = searchParams.get("workspaceId");
  const label = searchParams.get("label") || "Chat";
  const { user, loading, logout } = useAuth();

  const [title, setTitle] = useState(label);
  const [messages, setMessages] = useState<Message[]>([]);
  const [typingUser, setTypingUser] = useState<string | null>(null);
  const [searchQuery, setSearchQuery] = useState("");
  const [error, setError] = useState("");
  const wsRef = useRef<WebSocket | null>(null);

  const backHref = useMemo(() => {
    if (kind === "workspace" && workspaceId) return `/workspaces/${workspaceId}`;
    return "/chats";
  }, [kind, workspaceId]);

  const loadThreadMeta = useCallback(async () => {
    try {
      if (kind === "workspace" && workspaceId) {
        const chat = await getChat(workspaceId, chatId);
        setTitle(chat.name);
      } else if (kind === "room") {
        const room = await getPersonalRoom(chatId);
        setTitle(room.name);
      } else {
        setTitle(label);
      }
    } catch {
      setError("Chat not found");
    }
  }, [chatId, kind, label, workspaceId]);

  const loadMessages = useCallback(async () => {
    try {
      const res = kind === "workspace" && workspaceId
        ? await getMessages(workspaceId, chatId)
        : kind === "dm"
          ? await getDMMessages(chatId)
          : await getPersonalRoomMessages(chatId);
      setMessages(res.messages);
    } catch {
      setError("Failed to load messages");
    }
  }, [chatId, kind, workspaceId]);

  useEffect(() => {
    if (!user) return;
    loadThreadMeta();
    loadMessages();
  }, [user, loadMessages, loadThreadMeta]);

  useEffect(() => {
    if (!user) return;
    let ws: WebSocket | null = null;
    let cancelled = false;

    fetchWsToken().then((token) => {
      if (cancelled || !token) return;
      const wsPath = kind === "workspace" && workspaceId
        ? `/api/v1/workspaces/${workspaceId}/chats/${chatId}/ws`
        : kind === "dm"
          ? `/api/v1/dms/${chatId}/ws`
          : `/api/v1/rooms/${chatId}/ws`;
      ws = new WebSocket(`${getWsBase()}${wsPath}?token=${token}`);
      wsRef.current = ws;

      ws.onmessage = (event) => {
        try {
          const data: WSEvent = JSON.parse(event.data);
          if (data.type === "message" && data.id) {
            const messageId = data.id;
            setMessages((prev) => [
              ...prev,
              {
                id: messageId,
                chat_id: data.chat_id || chatId,
                sender_id: data.sender_id || "",
                sender_name: data.sender_name || "",
                sender_display_name: data.sender_display_name || null,
                sender_type: (data.sender_type as "human" | "persona") || "human",
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
          setError("Realtime connection failed");
        }
      };
    });

    return () => {
      cancelled = true;
      ws?.close();
      wsRef.current = null;
    };
  }, [chatId, kind, user, workspaceId]);

  const handleSend = useCallback(async (content: string) => {
    try {
      if (kind === "workspace" && workspaceId) {
        await sendMessage(workspaceId, chatId, content);
      } else if (kind === "dm") {
        await sendDMMessage(chatId, content);
      } else {
        await sendPersonalRoomMessage(chatId, content);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to send message");
    }
  }, [chatId, kind, workspaceId]);

  if (loading) return <div className="min-h-screen flex items-center justify-center text-muted">Loading...</div>;
  if (!user) { router.push("/login"); return null; }

  return (
    <AppShell user={user} onLogout={logout}>
      <div className="flex flex-col h-full">
        <div className="bg-surface border-b border-border px-4 py-2 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <Link href={backHref} className="text-dim hover:text-foreground text-sm">&larr;</Link>
            <h1 className="text-foreground font-medium">{title}</h1>
            {kind === "workspace" && workspaceId && <span className="text-xs text-muted">Workspace chat</span>}
            {kind === "dm" && <span className="text-xs text-muted">Direct message</span>}
          </div>
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
          isSearching={false}
        />
        <div className="p-4 border-t border-border bg-surface">
          <ChatInput onSend={handleSend} />
        </div>
      </div>
    </AppShell>
  );
}
