"use client";

import { useCallback, useRef, useState } from "react";

interface ChatInputProps {
  onSend: (content: string) => void;
  onTyping?: () => void;
  disabled?: boolean;
}

export default function ChatInput({
  onSend,
  onTyping,
  disabled,
}: ChatInputProps) {
  const [value, setValue] = useState("");
  const typingTimeoutRef = useRef<NodeJS.Timeout | null>(null);

  const handleSubmit = useCallback(
    (e: React.FormEvent) => {
      e.preventDefault();
      const trimmed = value.trim();
      if (!trimmed) return;
      onSend(trimmed);
      setValue("");
    },
    [value, onSend]
  );

  const handleChange = useCallback(
    (e: React.ChangeEvent<HTMLInputElement>) => {
      setValue(e.target.value);
      if (onTyping) {
        if (typingTimeoutRef.current) clearTimeout(typingTimeoutRef.current);
        typingTimeoutRef.current = setTimeout(() => {
          onTyping();
        }, 300);
      }
    },
    [onTyping]
  );

  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent) => {
      if (e.key === "Enter" && !e.shiftKey) {
        e.preventDefault();
        const trimmed = value.trim();
        if (!trimmed) return;
        onSend(trimmed);
        setValue("");
      }
    },
    [value, onSend]
  );

  return (
    <form onSubmit={handleSubmit} className="flex gap-2">
      <input
        type="text"
        value={value}
        onChange={handleChange}
        onKeyDown={handleKeyDown}
        disabled={disabled}
        placeholder="Type a message..."
        className="flex-1 bg-gray-800 border border-gray-700 rounded-lg px-4 py-2.5 text-sm text-white placeholder-gray-500 focus:outline-none focus:border-blue-500"
      />
      <button
        type="submit"
        disabled={disabled || !value.trim()}
        className="bg-blue-600 hover:bg-blue-500 disabled:opacity-50 disabled:hover:bg-blue-600 text-white px-4 py-2.5 rounded-lg text-sm font-medium"
      >
        Send
      </button>
    </form>
  );
}
