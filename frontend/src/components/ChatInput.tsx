"use client";

import { useCallback, useRef, useState } from "react";
import { uploadFile, uploadPersonalFile } from "../lib/api";

interface ChatInputProps {
  onSend: (content: string) => void;
  onTyping?: () => void;
  disabled?: boolean;
  workspaceId?: string | null;
}

export default function ChatInput({
  onSend,
  onTyping,
  disabled,
  workspaceId,
}: ChatInputProps) {
  const [value, setValue] = useState("");
  const [uploading, setUploading] = useState(false);
  const typingTimeoutRef = useRef<NodeJS.Timeout | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

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

  const handleFileUpload = useCallback(async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setUploading(true);
    try {
      const result = workspaceId
        ? await uploadFile(workspaceId, file)
        : await uploadPersonalFile(file);
      // Insert as markdown link/image
      const isImage = result.content_type.startsWith("image/");
      const link = isImage ? `![${result.name}](${result.url})` : `[${result.name}](${result.url})`;
      setValue((prev) => prev ? `${prev} ${link}` : link);
    } catch {
      // Silently fail — storage may not be configured
    }
    setUploading(false);
    if (fileInputRef.current) fileInputRef.current.value = "";
  }, [workspaceId]);

  return (
    <form onSubmit={handleSubmit} className="flex gap-2">
      <input
        ref={fileInputRef}
        type="file"
        className="hidden"
        onChange={handleFileUpload}
      />
      <button
        type="button"
        onClick={() => fileInputRef.current?.click()}
        disabled={disabled || uploading}
        className="bg-raised hover:bg-border border border-border text-muted hover:text-foreground px-3 py-2.5 rounded-lg text-sm disabled:opacity-50"
        title="Upload file"
      >
        {uploading ? "..." : "+"}
      </button>
      <input
        type="text"
        value={value}
        onChange={handleChange}
        onKeyDown={handleKeyDown}
        disabled={disabled}
        placeholder="Type a message..."
        className="flex-1 bg-raised border border-border rounded-lg px-4 py-2.5 text-sm text-foreground placeholder-muted focus:outline-none focus:border-brand"
      />
      <button
        type="submit"
        disabled={disabled || !value.trim()}
        className="bg-brand hover:bg-brand-hover disabled:opacity-50 disabled:hover:bg-brand text-white px-4 py-2.5 rounded-lg text-sm font-medium"
      >
        Send
      </button>
    </form>
  );
}
