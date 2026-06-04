"use client";

import { useParams, useSearchParams } from "next/navigation";
import { Suspense, useEffect, useRef, useState } from "react";

import ChatPanel from "../../../../../components/agents/ChatPanel";

// Agents: the primary way to use Stash is through your own agent. The first tab
// (unclosable) explains how to connect the CLI / MCP / API; extra tabs are
// multi-turn chats over your sources. Each chat is a stored Session, so its
// session_id + the open tabs persist across reloads.
type ChatTab = { id: number; sessionId: string | null; title: string };
type PersistedTabs = { chats: ChatTab[]; nextId: number; active: "connect" | number };

function tabsKey(workspaceId: string): string {
  return `stash_agent_tabs:${workspaceId}`;
}

export default function AgentsPage() {
  return (
    <Suspense fallback={null}>
      <AgentsPageInner />
    </Suspense>
  );
}

function AgentsPageInner() {
  const params = useParams();
  const workspaceId = params.workspaceId as string;

  const searchParams = useSearchParams();
  const [chats, setChats] = useState<ChatTab[]>([]);
  const [nextId, setNextId] = useState(1);
  const [active, setActive] = useState<"connect" | number>("connect");
  const restored = useRef(false);
  // Resume a specific chat from a `?resume=<sessionId>` link (e.g. from the
  // Agent Sessions list).

  // Restore open tabs (+ their session ids) for this workspace, then apply any
  // `?resume=<sessionId>` in one pass so a resume can't race the restore into a
  // duplicate tab.
  useEffect(() => {
    if (restored.current) return;
    restored.current = true;
    let chats: ChatTab[] = [];
    let next = 1;
    let active: "connect" | number = "connect";
    try {
      const raw = window.localStorage.getItem(tabsKey(workspaceId));
      if (raw) {
        const p = JSON.parse(raw) as PersistedTabs;
        if (Array.isArray(p.chats)) {
          chats = p.chats;
          next = p.nextId ?? p.chats.length + 1;
          active = p.active ?? "connect";
        }
      }
    } catch {
      /* ignore malformed cache */
    }
    const resume = searchParams.get("resume");
    if (resume) {
      const existing = chats.find((t) => t.sessionId === resume);
      if (existing) {
        active = existing.id;
      } else {
        chats = [...chats, { id: next, sessionId: resume, title: "Chat" }];
        active = next;
        next += 1;
      }
    }
    setChats(chats);
    setNextId(next);
    setActive(active);
  }, [workspaceId, searchParams]);

  // Persist whenever tabs change (after the initial restore).
  useEffect(() => {
    if (!restored.current) return;
    try {
      window.localStorage.setItem(
        tabsKey(workspaceId),
        JSON.stringify({ chats, nextId, active } satisfies PersistedTabs),
      );
    } catch {
      /* storage unavailable */
    }
  }, [workspaceId, chats, nextId, active]);

  function newChat() {
    const id = nextId;
    setChats((c) => [...c, { id, sessionId: null, title: `Chat ${id}` }]);
    setNextId((n) => n + 1);
    setActive(id);
  }

  function closeChat(id: number) {
    setChats((c) => c.filter((t) => t.id !== id));
    setActive((a) => (a === id ? "connect" : a));
  }

  function setChatSession(id: number, sessionId: string) {
    setChats((c) => c.map((t) => (t.id === id ? { ...t, sessionId } : t)));
  }

  return (
    <div className="scroll-thin flex-1 overflow-y-auto">
      <div
        className={
          // Chats want room to breathe (ChatGPT-style); the Connect guide reads
          // better narrow.
          "mx-auto w-full px-8 py-8 " + (active === "connect" ? "max-w-3xl" : "max-w-5xl")
        }
      >
        <div className="flex items-center gap-1 border-b border-border">
          <button
            type="button"
            onClick={() => setActive("connect")}
            className={tabClass(active === "connect")}
          >
            Connect your agent
          </button>
          {chats.map((t) => (
            <span key={t.id} className={tabClass(active === t.id)}>
              <button type="button" onClick={() => setActive(t.id)} className="outline-none">
                {t.title}
              </button>
              <button
                type="button"
                aria-label="Close chat"
                onClick={() => closeChat(t.id)}
                className="ml-1 text-muted hover:text-error"
              >
                ×
              </button>
            </span>
          ))}
          <button
            type="button"
            onClick={newChat}
            aria-label="New chat"
            className="px-3 py-2 text-[16px] text-muted hover:text-foreground"
          >
            ＋
          </button>
        </div>

        <div className="pt-5">
          {/* All panels stay mounted (toggled with `hidden`) so a chat keeps
              its transcript, scroll, and in-flight stream when you switch tabs. */}
          <div className={active === "connect" ? "" : "hidden"}>
            <ConnectGuide />
          </div>
          {chats.map((t) => (
            <div key={t.id} className={active === t.id ? "" : "hidden"}>
              <ChatPanel
                workspaceId={workspaceId}
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
    "flex items-center gap-0.5 rounded-t-md border border-b-0 px-3 py-2 text-[12.5px] -mb-px " +
    (activeTab
      ? "border-border bg-base font-semibold text-foreground"
      : "border-transparent bg-surface text-dim hover:text-foreground")
  );
}

function Step({ n, title, children }: { n: number; title: string; children: React.ReactNode }) {
  return (
    <div className="mb-5">
      <div className="text-[13.5px] font-semibold text-foreground">
        {n}. {title}
      </div>
      <div className="mt-2 text-[13px] text-dim">{children}</div>
    </div>
  );
}

function Code({ children }: { children: string }) {
  return (
    <pre className="mt-2 overflow-x-auto rounded-md border border-border bg-surface px-3 py-2 font-mono text-[12px] text-foreground">
      {children}
    </pre>
  );
}

function ConnectGuide() {
  return (
    <div className="rounded-xl border border-border bg-base p-5">
      <div className="mb-5 rounded-lg border border-border bg-surface/60 p-4 text-[13px] text-dim">
        <div className="text-[13.5px] font-semibold text-foreground">What this sets up</div>
        <p className="mt-1.5">
          Installing the CLI adds a small <strong>plugin with hooks</strong> to your coding agent
          (Claude Code, Codex, and friends). It works in two directions:
        </p>
        <ul className="mt-2 list-disc space-y-1.5 pl-5">
          <li>
            <strong>Push (hooks)</strong> — as your agent runs, the hooks automatically stream each
            session&rsquo;s transcript, the files it touches, and the artifacts it produces into your
            Stash. Nothing to remember to save; your history lands in{" "}
            <strong>Agent Sessions</strong> on its own.
          </li>
          <li>
            <strong>Pull (search &amp; query)</strong> — everything in your Stash (sessions, files,
            pages, tables, connected sources) is indexed, so your agent can search it and answer
            questions grounded on your own work.
          </li>
        </ul>
      </div>
      <Step n={1} title="Install the Stash CLI">
        The CLI is the preferred way for your agent to reach Stash — it installs the plugin and hooks
        above.
        <Code>{`bash -c "$(curl -fsSL https://joinstash.ai/install)"`}</Code>
      </Step>
      <Step n={2} title="Sign in">
        Authorize the CLI for this account — it prints a consent URL.
        <Code>stash signin</Code>
      </Step>
      <Step n={3} title="Point your agent at it (MCP)">
        Add Stash as an MCP server so your agent can navigate and search every source.
        See the{" "}
        <a className="text-[var(--color-brand-700)] underline" href="https://joinstash.ai/docs/mcp" target="_blank" rel="noopener noreferrer">
          MCP setup docs
        </a>
        .
      </Step>
      <Step n={4} title="Or call the API directly">
        Create a personal API key in{" "}
        <a className="text-[var(--color-brand-700)] underline" href="/settings">
          Settings
        </a>{" "}
        and read the{" "}
        <a className="text-[var(--color-brand-700)] underline" href="https://joinstash.ai/docs/api" target="_blank" rel="noopener noreferrer">
          API docs
        </a>
        .
      </Step>
      <div className="mt-4 rounded-md bg-surface px-3 py-2 text-[12.5px] text-muted">
        Prefer the browser? Open a chat tab above and ask across your sources right here.
      </div>
    </div>
  );
}
