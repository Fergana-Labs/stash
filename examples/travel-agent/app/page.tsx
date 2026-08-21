"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { TRAVELLERS, travellerById } from "@/lib/travellers";
import { Answer } from "./answer";
import { Compass, Menu, Plus, Send, Stash, Stop, Tick } from "./icons";

// An assistant turn is a run of parts in the order they happened: text it
// said, and each read it made against Stash. A user turn is one text part.
type Part =
  | { kind: "text"; text: string }
  | { kind: "read"; id: string; script: string; state: "running" | "ok" | "empty"; summary?: string };
type Message = { role: "user" | "assistant"; parts: Part[] };
type Conversation = { id: string; title: string };

function text(message: Message): string {
  return message.parts
    .filter((part): part is { kind: "text"; text: string } => part.kind === "text")
    .map((part) => part.text)
    .join("\n\n");
}

export default function Page() {
  const [travellerId, setTravellerId] = useState(TRAVELLERS[0].id);
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [sessionId, setSessionId] = useState(() => newSessionId(TRAVELLERS[0].id));
  const [messages, setMessages] = useState<Message[]>([]);
  const [draft, setDraft] = useState("");
  const [streaming, setStreaming] = useState(false);
  const [opening, setOpening] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);
  const [menuOpen, setMenuOpen] = useState(false);
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const abortRef = useRef<AbortController | null>(null);
  const workspaceRef = useRef<HTMLDivElement>(null);
  const bottomRef = useRef<HTMLDivElement>(null);
  const traveller = travellerById(travellerId);

  const loadConversations = useCallback(async (tenant: string) => {
    const res = await fetch(`/api/conversations?tenant=${encodeURIComponent(tenant)}`);
    const body = await res.json();
    if (!res.ok) return setNotice(body.error);
    setConversations(body.conversations);
  }, []);

  useEffect(() => {
    void loadConversations(travellerId);
  }, [travellerId, loadConversations]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  // Clicking anywhere off the account switcher closes it. pointerdown rather
  // than click, so the press that opened the menu is long past by the time this
  // listener exists; clicks inside the switcher are left to its own handlers.
  useEffect(() => {
    if (!menuOpen) return;
    function closeOnOutsidePress(event: PointerEvent) {
      if (!workspaceRef.current?.contains(event.target as Node)) setMenuOpen(false);
    }
    document.addEventListener("pointerdown", closeOnOutsidePress);
    return () => document.removeEventListener("pointerdown", closeOnOutsidePress);
  }, [menuOpen]);

  // The window keeps no memory of its own: a new chat is an empty page here and
  // Atlas still knows this traveller, because the memory lives in Stash rather
  // than in this tab.
  function startChat(tenant: string) {
    setSessionId(newSessionId(tenant));
    setMessages([]);
    setNotice(null);
    setSidebarOpen(false);
  }

  function switchTraveller(id: string) {
    setTravellerId(id);
    setMenuOpen(false);
    startChat(id);
  }

  async function openConversation(conversation: Conversation) {
    setSessionId(conversation.id);
    setMessages([]);
    setOpening(true);
    setNotice(null);
    setSidebarOpen(false);
    const res = await fetch(
      `/api/conversations?tenant=${encodeURIComponent(travellerId)}&session=${encodeURIComponent(conversation.id)}`,
    );
    const body = await res.json();
    setOpening(false);
    if (!res.ok) return setNotice(body.error);
    setMessages(
      (body.turns as { role: "user" | "assistant"; content: string }[]).map((turn) => ({
        role: turn.role,
        parts: [{ kind: "text" as const, text: turn.content }],
      })),
    );
  }

  async function send(draftText: string) {
    const question = draftText.trim();
    if (!question || streaming) return;

    const history: Message[] = [...messages, { role: "user", parts: [{ kind: "text", text: question }] }];
    setMessages([...history, { role: "assistant", parts: [] }]);
    setDraft("");
    setNotice(null);
    setStreaming(true);

    const controller = new AbortController();
    abortRef.current = controller;
    // The assistant turn is rebuilt from this array on every event, so the
    // thread shows reads and text in the order the agent produced them.
    const parts: Part[] = [];
    try {
      const res = await fetch("/api/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          tenant: travellerId,
          messages: history.map((m) => ({ role: m.role, content: text(m) })),
        }),
        signal: controller.signal,
      });
      if (!res.ok) throw new Error((await res.json()).error);
      for await (const event of eventLines(res.body!, controller.signal)) {
        if (event.type === "text") {
          const last = parts[parts.length - 1];
          if (last?.kind === "text") last.text += event.delta;
          else parts.push({ kind: "text", text: event.delta });
        } else if (event.type === "tool") {
          parts.push({ kind: "read", id: event.id, script: event.script, state: "running" });
        } else if (event.type === "tool_result") {
          const read = parts.find((part) => part.kind === "read" && part.id === event.id);
          if (read?.kind === "read") {
            read.state = event.ok ? "ok" : "empty";
            read.summary = event.summary;
          }
        }
        setMessages([...history, { role: "assistant", parts: [...parts] }]);
      }
    } catch (e) {
      // Stopping is the reader throwing, and it keeps whatever arrived first.
      if (!controller.signal.aborted) {
        console.error(e);
        setNotice(e instanceof Error ? e.message : String(e));
        setMessages(history);
      }
    } finally {
      setStreaming(false);
      abortRef.current = null;
    }

    const reply = parts
      .filter((part): part is { kind: "text"; text: string } => part.kind === "text")
      .map((part) => part.text)
      .join("\n\n");
    if (!reply.trim()) return;
    const recorded = await fetch("/api/record", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        tenant: travellerId,
        tenantName: traveller.name,
        session: sessionId,
        question,
        reply,
      }),
    });
    if (!recorded.ok) return setNotice((await recorded.json()).error);
    await loadConversations(travellerId);
  }

  const waiting = streaming && !messages[messages.length - 1]?.parts.length;

  return (
    <div className="app">
      {sidebarOpen && <div className="overlay" onClick={() => setSidebarOpen(false)} />}

      <aside className={sidebarOpen ? "sidebar open" : "sidebar"}>
        <div className="brand">
          <Compass />
          <span className="brand-name">Atlas</span>
        </div>

        <button className="new-chat" onClick={() => startChat(travellerId)}>
          <Plus />
          New chat
        </button>

        <div className="section-label">Recent</div>
        <div className="recents">
          {conversations.length === 0 && (
            <div className="recents-empty">Your trips with Atlas show up here.</div>
          )}
          {conversations.map((c) => (
            <button
              key={c.id}
              className={c.id === sessionId ? "recent active" : "recent"}
              onClick={() => void openConversation(c)}
            >
              {c.title}
            </button>
          ))}
        </div>

        <div className="workspace" ref={workspaceRef}>
          {menuOpen && (
            <div className="menu">
              <div className="menu-label">Switch account</div>
              {TRAVELLERS.map((t) => (
                <button key={t.id} className="menu-item" onClick={() => switchTraveller(t.id)}>
                  <span className="avatar">{initials(t.name)}</span>
                  {t.name}
                  {t.id === travellerId && (
                    <span className="menu-check">
                      <Tick />
                    </span>
                  )}
                </button>
              ))}
            </div>
          )}
          <button className="workspace-button" onClick={() => setMenuOpen(!menuOpen)}>
            <span className="avatar">{initials(traveller.name)}</span>
            <span className="workspace-text">
              <div className="workspace-name">{traveller.name}</div>
              <div className="workspace-plan">{traveller.email}</div>
            </span>
          </button>
        </div>
      </aside>

      <main className="main">
        <div className="topbar">
          <button className="icon-button" onClick={() => setSidebarOpen(true)}>
            <Menu />
          </button>
          <span className="brand-name">Atlas</span>
          <button
            className="icon-button"
            style={{ marginLeft: "auto" }}
            onClick={() => startChat(travellerId)}
          >
            <Plus />
          </button>
        </div>

        <div className="thread">
          <div className="thread-inner">
            {opening ? null : messages.length === 0 ? (
              <div className="welcome">
                <h1 className="greeting">Where do you want to go?</h1>
                <p className="greeting-sub">
                  Tell me who is travelling and roughly when, and I will work out the rest.
                </p>
              </div>
            ) : (
              messages.map((m, i) =>
                m.role === "user" ? (
                  <div key={i} className="turn user">
                    <div className="bubble">{text(m)}</div>
                  </div>
                ) : (
                  <div key={i} className="turn">
                    <span className="mark">
                      <Compass />
                    </span>
                    <div className="answer">
                      {m.parts.map((part, j) =>
                        part.kind === "read" ? (
                          <div key={j} className={`read read-${part.state}`}>
                            <Stash />
                            <span className="read-label">Read from Stash</span>
                            <code>{part.script}</code>
                            <span className="read-summary">{part.summary ?? "…"}</span>
                          </div>
                        ) : (
                          <Answer key={j} text={part.text} />
                        ),
                      )}
                      {!m.parts.length &&
                        (waiting && (
                          <span className="dots">
                            <span>·</span>
                            <span>·</span>
                            <span>·</span>
                          </span>
                        ))}
                    </div>
                  </div>
                ),
              )
            )}
            <div ref={bottomRef} />
          </div>
        </div>

        <div className="composer-wrap">
          <div className="composer">
            <textarea
              rows={1}
              value={draft}
              placeholder="Message Atlas…"
              onChange={(e) => {
                setDraft(e.target.value);
                e.target.style.height = "auto";
                e.target.style.height = `${e.target.scrollHeight}px`;
              }}
              onKeyDown={(e) => {
                if (e.key !== "Enter" || e.shiftKey) return;
                e.preventDefault();
                void send(draft);
              }}
            />
            {streaming ? (
              <button className="send" onClick={() => abortRef.current?.abort()} title="Stop">
                <Stop />
              </button>
            ) : (
              <button className="send" disabled={!draft.trim()} onClick={() => void send(draft)}>
                <Send />
              </button>
            )}
          </div>
          <div className={notice ? "footnote warn" : "footnote"}>
            {notice ?? "Atlas can be wrong about fares and visa timelines. Check before you book."}
          </div>
        </div>
      </main>
    </div>
  );
}

/** One JSON object per line, as the agent produces them. */
async function* eventLines(
  body: ReadableStream<Uint8Array>,
  signal: AbortSignal,
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
): AsyncGenerator<any> {
  const reader = body.getReader();
  const decoder = new TextDecoder();
  let pending = "";
  while (!signal.aborted) {
    const { done, value } = await reader.read();
    if (done) return;
    pending += decoder.decode(value, { stream: true });
    const lines = pending.split("\n");
    pending = lines.pop()!;
    for (const line of lines) if (line.trim()) yield JSON.parse(line);
  }
}

// A session belongs to one traveller, so the id carries the traveller: the
// second customer to reuse a bare id would be refused with a 400.
function newSessionId(tenant: string): string {
  return `${tenant}:${Math.random().toString(36).slice(2, 10)}`;
}

function initials(name: string): string {
  return name
    .split(" ")
    .slice(0, 2)
    .map((word) => word[0])
    .join("");
}
