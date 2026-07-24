"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";
import Markdown from "react-markdown";
import remarkGfm from "remark-gfm";

import {
  type ChatMessage,
  type Citation,
  agentTurnRunning,
  getAgentChat,
  streamAgentChat,
} from "@/lib/agentChat";
import { apiFetch } from "@/lib/api";

// A real multi-turn agent chat: a scrolling transcript + a composer. Enter
// sends, Shift+Enter inserts a newline. Each turn is persisted server-side
// (the chat is a stored Session), so `sessionId` lets a reopened tab reload
// its history. `onSessionId` fires when the server mints one on the first turn.
export default function ChatPanel({
  sessionId,
  onSessionId,
  agentId,
}: {
  sessionId: string | null;
  onSessionId: (id: string) => void;
  agentId?: string | null;
}) {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState("");
  const [streaming, setStreaming] = useState(false);
  const [status, setStatus] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loadedSession, setLoadedSession] = useState<string | null>(null);
  const scrollRef = useRef<HTMLDivElement>(null);
  const abortRef = useRef<AbortController | null>(null);

  // Restore an existing chat's history once when the tab mounts/points at a
  // session we haven't loaded yet.
  useEffect(() => {
    if (!sessionId || loadedSession === sessionId) return;
    setLoadedSession(sessionId);
    getAgentChat(sessionId)
      .then((msgs) => {
        if (msgs.length > 0) setMessages(msgs);
      })
      .catch(() => {});
  }, [sessionId, loadedSession]);

  // Turns run detached on the sandbox, so one can outlive the panel that
  // started it (closed tab, navigation). If this session's turn is still
  // running, watch for it to finish and pull the recorded reply.
  useEffect(() => {
    if (!sessionId || streaming) return;
    let stopped = false;
    void (async () => {
      if (!(await agentTurnRunning(sessionId).catch(() => false))) return;
      setStatus("Agent is still working…");
      while (!stopped && (await agentTurnRunning(sessionId).catch(() => false))) {
        await new Promise((resolve) => setTimeout(resolve, 3000));
      }
      if (stopped) return;
      setStatus(null);
      const msgs = await getAgentChat(sessionId).catch(() => null);
      if (msgs && !stopped) setMessages(msgs);
    })();
    return () => {
      stopped = true;
    };
  }, [sessionId, streaming]);

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
          sessionId,
          message,
          agentId,
          signal: controller.signal,
          onSession: (id) => {
            if (!sessionId) onSessionId(id);
          },
          onStatus: (stage) => {
            if (stage === "waking") setStatus("Starting your computer…");
          },
          onText: (delta) => {
            setStatus(null);
            patchAssistant((m) => ({ ...m, content: m.content + delta }));
          },
          onError: (message) => setError(message),
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
        setStatus(null);
        abortRef.current = null;
      }
    },
    [sessionId, streaming, onSessionId, agentId],
  );

  return (
    <div className="flex h-full min-h-[520px] flex-col rounded-xl border border-border bg-base">
      <div ref={scrollRef} className="scroll-thin flex-1 space-y-4 overflow-y-auto p-4">
        {messages.length === 0 && !streaming ? (
          <EmptyChatState onPrompt={(prompt) => void send(prompt)} />
        ) : (
          messages.map((m, i) => <MessageBubble key={i} message={m} />)
        )}
        {status && (
          <div className="flex items-center gap-2 px-1 text-[12px] text-dim">
            <span className="inline-block h-2 w-2 animate-pulse rounded-full bg-brand" />
            {status}
          </div>
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

const suggestedPrompts = [
  "Catch me up on my stash",
  "What changed recently?",
  "Find the planning docs",
];

function EmptyChatState({ onPrompt }: { onPrompt: (prompt: string) => void }) {
  return (
    <div className="flex min-h-full items-center justify-center px-2 py-8">
      <div className="w-full max-w-3xl">
        <div className="text-center">
          <div className="text-[20px] font-semibold text-foreground">
            Chat with your agent
          </div>
          <p className="mx-auto mt-2 max-w-xl text-[13px] leading-5 text-dim">
            Ask about files, sessions, pages, tables, and connected sources in your stash.
          </p>
        </div>

        <div className="mt-5 grid gap-2 sm:grid-cols-3">
          {suggestedPrompts.map((prompt) => (
            <button
              key={prompt}
              type="button"
              onClick={() => onPrompt(prompt)}
              className="min-h-12 cursor-pointer rounded-md border border-border bg-surface px-3 py-2 text-left text-[12.5px] leading-4 text-foreground hover:border-[var(--color-brand-300)] hover:bg-raised"
            >
              {prompt}
            </button>
          ))}
        </div>

        <div className="mt-7 border-t border-border pt-5 text-left">
          <div className="text-[13.5px] font-semibold text-foreground">
            Connect your local agent
          </div>
          <p className="mt-1.5 text-[13px] leading-5 text-dim">
            Install the CLI when you want Codex, Claude Code, or another coding agent to push
            sessions into Skill and search your stash directly.
          </p>
          <div className="mt-4 grid gap-4 md:grid-cols-2">
            <SetupStep n={1} title="Install the Skill CLI">
              <Code>{`bash -c "$(curl -fsSL https://joinstash.ai/install)"`}</Code>
            </SetupStep>
            <SetupStep n={2} title="Sign in">
              <Code>stash signin</Code>
            </SetupStep>
            <SetupStep n={3} title="Point your agent at Skill">
              <a
                className="text-[var(--color-brand-700)] underline"
                href="https://joinstash.ai/docs/mcp"
                target="_blank"
                rel="noopener noreferrer"
              >
                MCP setup docs
              </a>
            </SetupStep>
            <SetupStep n={4} title="Use the API directly">
              <a className="text-[var(--color-brand-700)] underline" href="/settings">
                Settings
              </a>
              <span className="text-dim"> and </span>
              <a
                className="text-[var(--color-brand-700)] underline"
                href="https://joinstash.ai/docs/api"
                target="_blank"
                rel="noopener noreferrer"
              >
                API docs
              </a>
            </SetupStep>
          </div>
        </div>
      </div>
    </div>
  );
}

function SetupStep({
  n,
  title,
  children,
}: {
  n: number;
  title: string;
  children: React.ReactNode;
}) {
  return (
    <div>
      <div className="text-[12.5px] font-semibold text-foreground">
        {n}. {title}
      </div>
      <div className="mt-1.5 text-[12.5px] text-dim">{children}</div>
    </div>
  );
}

function Code({ children }: { children: string }) {
  return (
    <pre className="overflow-x-auto rounded-md border border-border bg-surface px-2.5 py-1.5 font-mono text-[11.5px] text-foreground">
      {children}
    </pre>
  );
}

const chipLinkClass =
  "font-mono underline decoration-dotted underline-offset-2 hover:text-foreground";

// A grounding citation, linked to what it names: web fetches open the page,
// app targets navigate in place, and VFS reads resolve their path to the
// object's route on click (the stream only carries the path).
function CitationChip({ citation }: { citation: Citation }) {
  const router = useRouter();
  const [resolving, setResolving] = useState(false);

  if (citation.href && citation.href.startsWith("http")) {
    return (
      <a href={citation.href} target="_blank" rel="noreferrer" className={chipLinkClass}>
        {citation.label}
      </a>
    );
  }
  if (citation.href) {
    return (
      <Link href={citation.href} className={chipLinkClass}>
        {citation.label}
      </Link>
    );
  }
  if (citation.vfsPath) {
    const open = async () => {
      if (resolving) return;
      setResolving(true);
      try {
        const { app_url } = await apiFetch<{ app_url: string | null }>(
          `/api/v1/me/vfs/resolve?path=${encodeURIComponent(citation.vfsPath ?? "")}`,
        );
        if (app_url) router.push(app_url);
      } catch {
        // A stale citation (the object was deleted since the chat) resolves
        // 404 — the chip stays inert rather than crashing the panel.
      } finally {
        setResolving(false);
      }
    };
    return (
      <button type="button" onClick={open} className={`${chipLinkClass} cursor-pointer`}>
        {citation.label}
      </button>
    );
  }
  return <span className="font-mono">{citation.label}</span>;
}

// User turns get a right-aligned bubble; assistant turns render inline across
// the full width (Claude Code / Codex style) as markdown.
function MessageBubble({ message }: { message: ChatMessage }) {
  if (message.role === "user") {
    return (
      <div className="flex justify-end">
        <div className="max-w-[85%] rounded-2xl bg-[var(--color-brand-600)] px-3.5 py-2 text-[13px] leading-relaxed whitespace-pre-wrap text-white">
          {message.content}
        </div>
      </div>
    );
  }
  return (
    <div className="text-[13px] leading-relaxed text-foreground">
      {message.content ? (
        <div className="markdown-content">
          <Markdown remarkPlugins={[remarkGfm]}>{message.content}</Markdown>
        </div>
      ) : (
        <span className="inline-block h-3 w-1.5 animate-pulse bg-brand align-baseline" />
      )}
      {message.citations && message.citations.length > 0 && (
        <div className="mt-2 border-t border-border-subtle pt-2 text-[11px] text-muted-foreground">
          <span className="font-medium text-foreground">Grounded on:</span>{" "}
          {message.citations.map((c, i) => (
            <span key={c.id}>
              {i > 0 && ", "}
              <CitationChip citation={c} />
            </span>
          ))}
        </div>
      )}
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
          placeholder="Ask your agent anything..."
          className="flex-1 resize-none rounded-md border border-border bg-base px-3 py-2 text-[13px] text-foreground placeholder:text-muted-foreground focus:border-brand focus:outline-none"
        />
        <button
          type="button"
          onClick={onSend}
          disabled={disabled || !value.trim()}
          className="cursor-pointer rounded-md bg-brand px-4 py-2 text-[13px] font-medium text-white hover:bg-brand-hover disabled:cursor-not-allowed disabled:opacity-60"
        >
          Send
        </button>
      </div>
    </div>
  );
}
