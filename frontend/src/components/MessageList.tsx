"use client";

import { useEffect, useRef } from "react";
import { Message } from "../lib/types";
import ChatMessage from "./ChatMessage";

interface MessageListProps {
  messages: Message[];
  currentUserId: string | null;
  typingUser: string | null;
  searchQuery: string;
  onSearchChange: (query: string) => void;
  isSearching: boolean;
}

export default function MessageList({
  messages,
  currentUserId,
  typingUser,
  searchQuery,
  onSearchChange,
  isSearching,
}: MessageListProps) {
  const bottomRef = useRef<HTMLDivElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!searchQuery) {
      bottomRef.current?.scrollIntoView({ behavior: "smooth" });
    }
  }, [messages.length, searchQuery]);

  return (
    <div className="flex-1 flex flex-col overflow-hidden">
      <div className="px-4 py-2 border-b border-gray-800">
        <div className="relative">
          <input
            type="text"
            value={searchQuery}
            onChange={(e) => onSearchChange(e.target.value)}
            placeholder="Search messages..."
            className="w-full bg-gray-800 border border-gray-700 rounded px-3 py-1.5 pl-8 text-sm text-white focus:outline-none focus:border-blue-500"
          />
          <svg
            className="absolute left-2.5 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-gray-500"
            fill="none"
            stroke="currentColor"
            viewBox="0 0 24 24"
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth={2}
              d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z"
            />
          </svg>
          {searchQuery && (
            <button
              onClick={() => onSearchChange("")}
              className="absolute right-2 top-1/2 -translate-y-1/2 text-gray-500 hover:text-gray-300 text-xs"
            >
              Clear
            </button>
          )}
        </div>
        {searchQuery && (
          <div className="text-xs text-gray-500 mt-1">
            {isSearching
              ? "Searching..."
              : `${messages.length} result${messages.length !== 1 ? "s" : ""}`}
          </div>
        )}
      </div>
      <div ref={containerRef} className="flex-1 overflow-y-auto px-4 py-3">
        {messages.length === 0 ? (
          <div className="flex items-center justify-center h-full text-gray-500 text-sm">
            {searchQuery
              ? "No messages found."
              : "No messages yet. Start the conversation!"}
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
        {typingUser && !searchQuery && (
          <div className="text-xs text-gray-500 mt-1 animate-pulse">
            {typingUser} is typing...
          </div>
        )}
        <div ref={bottomRef} />
      </div>
    </div>
  );
}
