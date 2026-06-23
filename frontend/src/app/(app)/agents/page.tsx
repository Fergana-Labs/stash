"use client";

import { useSearchParams } from "next/navigation";
import { Suspense, useEffect, useRef, useState } from "react";

import ChatPanel from "@/components/agents/ChatPanel";

// Agents is a chat surface. Each tab is a stored Session, so its session_id and
// the open tabs persist across reloads.
type ChatTab = { id: number; sessionId: string | null; title: string };
type PersistedTabs = { chats: ChatTab[]; nextId: number; active: number };

const firstChatId = 1;
const tabsKey = "stash_agent_chat_tabs";

function defaultTabs(): PersistedTabs {
  return {
    chats: [{ id: firstChatId, sessionId: null, title: "Chat" }],
    nextId: firstChatId + 1,
    active: firstChatId,
  };
}

export default function AgentsPage() {
  return (
    <Suspense fallback={null}>
      <AgentsPageInner />
    </Suspense>
  );
}

function AgentsPageInner() {
  const searchParams = useSearchParams();
  const initialTabs = defaultTabs();
  const [chats, setChats] = useState<ChatTab[]>(initialTabs.chats);
  const [nextId, setNextId] = useState(initialTabs.nextId);
  const [active, setActive] = useState(initialTabs.active);
  const restored = useRef(false);
  // Resume a specific chat from a `?resume=<sessionId>` link (e.g. from the
  // Agent Sessions list).

  // Restore open tabs (+ their session ids), then apply any
  // `?resume=<sessionId>` in one pass so a resume can't race the restore into a
  // duplicate tab.
  useEffect(() => {
    if (restored.current) return;
    restored.current = true;
    let state = defaultTabs();
    try {
      const raw = window.localStorage.getItem(tabsKey);
      if (raw) {
        const p = JSON.parse(raw) as PersistedTabs;
        if (Array.isArray(p.chats) && p.chats.length > 0 && typeof p.active === "number") {
          const activeExists = p.chats.some((t) => t.id === p.active);
          state = {
            chats: p.chats,
            nextId: p.nextId ?? Math.max(...p.chats.map((t) => t.id)) + 1,
            active: activeExists ? p.active : p.chats[0].id,
          };
        }
      }
    } catch {
      /* ignore malformed cache */
    }
    const resume = searchParams.get("resume");
    if (resume) {
      const existing = state.chats.find((t) => t.sessionId === resume);
      if (existing) {
        state = { ...state, active: existing.id };
      } else {
        state = {
          chats: [...state.chats, { id: state.nextId, sessionId: resume, title: "Chat" }],
          active: state.nextId,
          nextId: state.nextId + 1,
        };
      }
    }
    setChats(state.chats);
    setNextId(state.nextId);
    setActive(state.active);
  }, [searchParams]);

  // Persist whenever tabs change (after the initial restore).
  useEffect(() => {
    if (!restored.current) return;
    try {
      window.localStorage.setItem(
        tabsKey,
        JSON.stringify({ chats, nextId, active } satisfies PersistedTabs),
      );
    } catch {
      /* storage unavailable */
    }
  }, [chats, nextId, active]);

  function newChat() {
    const id = nextId;
    setChats((c) => [...c, { id, sessionId: null, title: `Chat ${id}` }]);
    setNextId((n) => n + 1);
    setActive(id);
  }

  function closeChat(id: number) {
    if (chats.length === 1) return;
    const remaining = chats.filter((t) => t.id !== id);
    setChats(remaining);
    if (active === id) setActive(remaining[remaining.length - 1].id);
  }

  function setChatSession(id: number, sessionId: string) {
    setChats((c) => c.map((t) => (t.id === id ? { ...t, sessionId } : t)));
  }

  return (
    <div className="flex min-h-0 flex-1 flex-col overflow-hidden">
      <div className="mx-auto flex min-h-0 w-full max-w-5xl flex-1 flex-col px-4 py-5 sm:px-6 lg:px-8">
        <div className="mb-4 flex min-w-0 items-end justify-between gap-3">
          <div className="min-w-0">
            <h1 className="truncate text-[20px] font-semibold text-foreground">
              Chat with your agent
            </h1>
            <p className="mt-1 text-[13px] text-muted">
              Ask across all your stuff from one place.
            </p>
          </div>
          <a
            className="shrink-0 rounded-md border border-border px-3 py-1.5 text-[12.5px] font-medium text-dim hover:border-[var(--color-brand-300)] hover:bg-surface hover:text-foreground"
            href="https://joinstash.ai/docs/mcp"
            target="_blank"
            rel="noopener noreferrer"
          >
            Setup docs
          </a>
        </div>

        <div className="flex min-w-0 items-center gap-1 border-b border-border">
          {chats.map((t) => (
            <span key={t.id} className={tabClass(active === t.id)}>
              <button
                type="button"
                onClick={() => setActive(t.id)}
                className="min-w-0 cursor-pointer truncate outline-none"
              >
                {t.title}
              </button>
              {chats.length > 1 && (
                <button
                  type="button"
                  aria-label="Close chat"
                  onClick={() => closeChat(t.id)}
                  className="ml-1 cursor-pointer text-muted hover:text-error"
                >
                  ×
                </button>
              )}
            </span>
          ))}
          <button
            type="button"
            onClick={newChat}
            aria-label="New chat"
            className="cursor-pointer px-3 py-2 text-[16px] text-muted hover:text-foreground"
          >
            ＋
          </button>
        </div>

        <div className="min-h-0 flex-1 pt-4">
          {/* All panels stay mounted (toggled with `hidden`) so a chat keeps
              its transcript, scroll, and in-flight stream when you switch tabs. */}
          {chats.map((t) => (
            <div key={t.id} className={active === t.id ? "h-full" : "hidden"}>
              <ChatPanel
                sessionId={t.sessionId}
                onSessionId={(id) => setChatSession(t.id, id)}
              />
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

function tabClass(activeTab: boolean): string {
  return (
    "flex min-w-0 max-w-[180px] items-center gap-0.5 rounded-t-md border border-b-0 px-3 py-2 text-[12.5px] -mb-px " +
    (activeTab
      ? "border-border bg-base font-semibold text-foreground"
      : "border-transparent bg-surface text-dim hover:text-foreground")
  );
}
