"use client";

// /agents, ChatGPT-shaped: a sidebar of past chats and one conversation.
// No tabs, no explorer, no agent roster — this tab exists to ask the Stash,
// and every chat talks to the default agent. The conversation pane is
// AgentChatView, the same component stale workbench tabs render.

import { useCallback, useEffect, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { nanoid } from "nanoid";
import { SquarePen } from "lucide-react";
import { cn } from "@/lib/utils";
import { listMySessions, type SessionSummary } from "@/lib/api";
import { timeAgo } from "@/components/content/files-overview/build";
import AgentChatView from "./AgentChatView";

// Web chats mint `agent-<32 hex>` session ids; scheduled and curator runs use
// `agent-sched-…` / `agent-curate-…`, and coding-agent sessions have their own
// shapes. The id shape is the discriminator the whole agent surface uses.
const CHAT_SESSION_ID = /^agent-[0-9a-f]{32}$/;

function SideRow({
  label,
  annotation,
  active,
  onClick,
}: {
  label: string;
  annotation?: string;
  active: boolean;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={cn(
        "group flex w-full items-center gap-2 rounded-lg px-2.5 py-2 text-left text-[13px]",
        active ? "bg-raised font-medium text-foreground" : "text-foreground hover:bg-raised/60",
      )}
    >
      <span className="min-w-0 flex-1 truncate">{label}</span>
      {annotation && (
        <span className="shrink-0 text-[11px] text-muted-foreground">{annotation}</span>
      )}
    </button>
  );
}

export default function AgentsChat() {
  const router = useRouter();
  const searchParams = useSearchParams();
  // ?chat= selects a conversation (a stored session, a named agent, or a
  // staged `new-…` skill run); ?resume= is the deep link from a stored
  // session's "Resume in chat". A bare /agents is a fresh chat.
  const urlRef = searchParams.get("chat") ?? searchParams.get("resume");
  const [newRef, setNewRef] = useState(() => `new-${nanoid(5)}`);
  const selected = urlRef ?? newRef;
  // When a fresh chat's session is minted mid-stream, the URL flips to the
  // real id but the mounted view keeps its `new-…` ref — remounting on the
  // key change would drop the live stream. Cleared on any user selection.
  const [mintedFrom, setMintedFrom] = useState<{ sessionId: string; ref: string } | null>(null);
  const viewRef = mintedFrom?.sessionId === selected ? mintedFrom.ref : selected;

  const [chats, setChats] = useState<SessionSummary[] | null>(null);

  const loadChats = useCallback(async () => {
    const all = await listMySessions(100);
    setChats(all.filter((s) => CHAT_SESSION_ID.test(s.session_id)));
  }, []);
  useEffect(() => {
    loadChats().catch(() => setChats([]));
  }, [loadChats]);

  function select(ref: string) {
    setMintedFrom(null);
    router.replace(`/agents?chat=${encodeURIComponent(ref)}`);
  }

  function newChat() {
    setMintedFrom(null);
    setNewRef(`new-${nanoid(5)}`);
    router.replace("/agents");
  }

  return (
    <div className="flex h-full min-h-0">
      <aside className="flex w-[260px] shrink-0 flex-col border-r border-border bg-surface">
        <div className="p-2">
          <button
            type="button"
            onClick={newChat}
            className="flex w-full cursor-pointer items-center gap-2 rounded-lg border border-border bg-base px-3 py-2 text-[13px] font-medium text-foreground hover:bg-raised"
          >
            <SquarePen className="h-4 w-4" /> New chat
          </button>
        </div>
        <div className="scroll-thin min-h-0 flex-1 overflow-y-auto px-2 pb-3">
          <div className="px-2.5 pb-1 pt-2 text-[11px] font-medium uppercase tracking-wide text-muted-foreground">
            Chats
          </div>
          {chats?.map((s) => (
            <SideRow
              key={s.session_id}
              label={s.title || "Untitled chat"}
              annotation={timeAgo(s.last_event_at)}
              active={selected === s.session_id}
              onClick={() => select(s.session_id)}
            />
          ))}
          {chats !== null && chats.length === 0 && (
            <div className="px-2.5 py-1.5 text-[12px] text-muted-foreground">No chats yet</div>
          )}
        </div>
      </aside>
      <main className="min-w-0 flex-1 bg-base">
        {/* Keyed so switching conversations remounts a clean view. */}
        <AgentChatView
          key={viewRef}
          refId={viewRef}
          onSessionMinted={(id) => {
            setMintedFrom({ sessionId: id, ref: viewRef });
            router.replace(`/agents?chat=${encodeURIComponent(id)}`);
            void loadChats();
          }}
        />
      </main>
    </div>
  );
}
