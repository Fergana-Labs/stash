"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import {
  type ChatMessage,
  type Citation,
  getAgentChat,
  streamAgentChat,
} from "@/lib/agentChat";

// A real multi-turn agent chat: a scrolling transcript + a composer. Enter
// sends, Shift+Enter inserts a newline. Each turn is persisted server-side
// (the chat is a stored Session), so `sessionId` lets a reopened tab reload
// its history. `onSessionId` fires when the server mints one on the first turn.
export default function ChatPanel({
  workspaceId,
  sessionId,
  onSessionId,
}: {
  workspaceId: string;
  sessionId: string | null;
  onSessionId: (id: string) => void;
}) {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState("");
  const [streaming, setStreaming] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [loadedSession, setLoadedSession] = useState<string | null>(null);
  const scrollRef = useRef<HTMLDivElement>(null);
  const abortRef = useRef<AbortController | null>(null);

  // Restore an existing chat's history once when the tab mounts/points at a
  // session we haven't loaded yet.
  useEffect(() => {
    if (!sessionId || loadedSession === sessionId) return;
    setLoadedSession(sessionId);
    getAgentChat(workspaceId, sessionId)
      .then((msgs) => {
        if (msgs.length > 0) setMessages(msgs);
      })
      .catch(() => {});
  }, [workspaceId, sessionId, loadedSession]);

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight });
  }, [messages, streaming]);

  useEffect(() => () => abortRef.current?.abort(), []);

  const send = useCallback(
    async (text: string) => {
      const message = text.trim();
      if (!message || streaming) return;
      setInput("");
      setError(null);
      setStreaming(true);
      // Optimistically render the user turn and an empty assistant turn that
      // fills in as the stream arrives.
      setMessages((prev) => [
        ...prev,
        { role: "user", content: message },
        { role: "assistant", content: "", citations: [] },
      ]);

      const controller = new AbortController();
      abortRef.current = controller;

      const patchAssistant = (fn: (m: ChatMessage) => ChatMessage) =>
        setMessages((prev) => {
          const next = [...prev];
          for (let i = next.length - 1; i >= 0; i--) {
            if (next[i].role === "assistant") {
              next[i] = fn(next[i]);
              break;
            }
          }
          return next;
        });

      try {
        await streamAgentChat({
          workspaceId,
          sessionId,
          message,
          signal: controller.signal,
          onSession: (id) => {
            if (!sessionId) onSessionId(id);
          },
          onText: (delta) =>
            patchAssistant((m) => ({ ...m, content: m.content + delta })),
          onTool: (c: Citation) =>
            patchAssistant((m) =>
              m.citations?.some((x) => x.id === c.id)
                ? m
                : { ...m, citations: [...(m.citations ?? []), c] },
            ),
          onToolError: (id) =>
            patchAssistant((m) => ({
              ...m,
              citations: (m.citations ?? []).filter((x) => x.id !== id),
            })),
        });
      } catch (e) {
        if ((e as Error).name !== "AbortError") {
          setError(e instanceof Error ? e.message : String(e));
        }
      } finally {
        setStreaming(false);
        abortRef.current = null;
      }
    },
    [workspaceId, sessionId, streaming, onSessionId],
  );

  return (
    <div className="flex h-[60vh] flex-col rounded-xl border border-border bg-base">
      <div ref={scrollRef} className="scroll-thin flex-1 space-y-4 overflow-y-auto p-4">
        {messages.length === 0 && !streaming ? (
          <div className="flex h-full items-center justify-center px-6 text-center text-[13px] text-muted">
            Ask your agent anything about your sources — files, sessions, GitHub,
            Drive, Notion, Slack, Granola. It searches across everything.
          </div>
        ) : (
          messages.map((m, i) => <MessageBubble key={i} message={m} />)
        )}
        {error && (
          <div className="rounded-lg border border-error/30 bg-error/10 px-3 py-2 text-[12px] text-error">
            {error}
          </div>
        )}
      </div>

      <Composer
        value={input}
        onChange={setInput}
        onSend={() => void send(input)}
        disabled={streaming}
      />
    </div>
  );
}

function MessageBubble({ message }: { message: ChatMessage }) {
  const isUser = message.role === "user";
  return (
    <div className={isUser ? "flex justify-end" : "flex justify-start"}>
      <div
        className={
          "max-w-[85%] rounded-2xl px-3.5 py-2 text-[13px] leading-relaxed whitespace-pre-wrap " +
          (isUser
            ? "bg-[var(--color-brand-600)] text-white"
            : "border border-border bg-surface text-foreground")
        }
      >
        {message.content || (
          <span className="inline-block h-3 w-1.5 animate-pulse bg-brand align-baseline" />
        )}
        {!isUser && message.citations && message.citations.length > 0 && (
          <div className="mt-2 border-t border-border-subtle pt-2 text-[11px] text-muted">
            <span className="font-medium text-foreground">Grounded on:</span>{" "}
            {message.citations.map((c, i) => (
              <span key={c.id}>
                {i > 0 && ", "}
                <span className="font-mono">{c.label}</span>
              </span>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

function Composer({
  value,
  onChange,
  onSend,
  disabled,
}: {
  value: string;
  onChange: (v: string) => void;
  onSend: () => void;
  disabled: boolean;
}) {
  return (
    <div className="border-t border-border p-3">
      <div className="flex items-end gap-2">
        <textarea
          value={value}
          onChange={(e) => onChange(e.target.value)}
          onKeyDown={(e) => {
            // Enter sends; Shift+Enter (and IME composition) inserts a newline.
            if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) {
              e.preventDefault();
              onSend();
            }
          }}
          rows={2}
          placeholder="Message your agent…  (Enter to send, Shift+Enter for newline)"
          className="flex-1 resize-none rounded-md border border-border bg-base px-3 py-2 text-[13px] text-foreground placeholder:text-muted focus:border-brand focus:outline-none"
        />
        <button
          type="button"
          onClick={onSend}
          disabled={disabled || !value.trim()}
          className="rounded-md bg-brand px-4 py-2 text-[13px] font-medium text-white hover:bg-brand-hover disabled:cursor-not-allowed disabled:opacity-60"
        >
          Send
        </button>
      </div>
    </div>
  );
}
