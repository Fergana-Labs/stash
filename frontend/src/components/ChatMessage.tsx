"use client";

import { memo, useMemo } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { Message } from "../lib/types";

interface ChatMessageProps {
  message: Message;
  isOwn: boolean;
}

const remarkPlugins = [remarkGfm];

function ChatMessage({ message, isOwn }: ChatMessageProps) {
  if (message.message_type === "system") {
    return (
      <div className="text-center text-xs text-muted py-1">
        {message.content}
      </div>
    );
  }

  const time = new Date(message.created_at).toLocaleTimeString([], {
    hour: "2-digit",
    minute: "2-digit",
  });

  const renderedContent = useMemo(
    () => (
      <ReactMarkdown remarkPlugins={remarkPlugins}>
        {message.content}
      </ReactMarkdown>
    ),
    [message.content]
  );

  return (
    <div className={`flex gap-3 py-1.5 ${isOwn ? "flex-row-reverse" : ""}`}>
      <div
        className={`flex-shrink-0 w-8 h-8 rounded-full flex items-center justify-center text-xs font-bold ${
          message.sender_type === "persona"
            ? "bg-agent-muted text-agent"
            : "bg-human-muted text-human"
        }`}
      >
        {(message.sender_display_name || message.sender_name)
          .charAt(0)
          .toUpperCase()}
      </div>
      <div className={`max-w-[70%] ${isOwn ? "text-right" : ""}`}>
        <div
          className={`flex items-baseline gap-2 text-xs mb-0.5 ${
            isOwn ? "flex-row-reverse" : ""
          }`}
        >
          <span className="font-medium text-dim">
            {message.sender_display_name || message.sender_name}
          </span>
          <span className="text-muted">{time}</span>
          {message.sender_type === "persona" && (
            <span className="text-agent text-[10px]">BOT</span>
          )}
        </div>
        <div
          className={`inline-block rounded-lg px-3 py-2 text-sm markdown-content ${
            isOwn
              ? "bg-brand text-white"
              : "bg-raised text-foreground border border-border"
          }`}
        >
          {renderedContent}
        </div>
      </div>
    </div>
  );
}

export default memo(ChatMessage);
