"use client";

import { useEffect, useRef } from "react";
import { Message } from "../lib/types";
import ChatMessage from "./ChatMessage";

interface MessageListProps {
  messages: Message[];
  currentUserId: string | null;
  typingUser: string | null;
}

export default function MessageList({
  messages,
  currentUserId,
  typingUser,
}: MessageListProps) {
  const bottomRef = useRef<HTMLDivElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    // Auto-scroll to bottom on new messages
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages.length]);

  return (
    <div ref={containerRef} className="flex-1 overflow-y-auto px-4 py-3">
      {messages.length === 0 ? (
        <div className="flex items-center justify-center h-full text-gray-500 text-sm">
          No messages yet. Start the conversation!
        </div>
      ) : (
        <div className="space-y-1">
          {messages.map((msg) => (
            <ChatMessage
              key={msg.id}
              message={msg}
              isOwn={msg.sender_id === currentUserId}
            />
          ))}
        </div>
      )}
      {typingUser && (
        <div className="text-xs text-gray-500 mt-1 animate-pulse">
          {typingUser} is typing...
        </div>
      )}
      <div ref={bottomRef} />
    </div>
  );
}
