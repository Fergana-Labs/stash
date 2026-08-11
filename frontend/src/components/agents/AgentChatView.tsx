"use client";

import { useEffect, useState } from "react";
import ChatPanel from "@/components/agents/ChatPanel";
import AgentRunsView from "@/components/agents/AgentRunsView";
import { takeSkillRun } from "@/lib/skill-launch";
import { getAgent, type Agent } from "@/lib/api";

/** The agentId a conversation ref points at. Only a per-agent ref
 *  (`agent-<uuid>`) encodes one — stored session ids also start with `agent-`
 *  (chats mint `agent-<hex>`, runs `agent-curate|sched-…`), so match the full
 *  uuid shape instead of the prefix. Everything else is a chat-only ref. */
function agentIdFromRef(refId: string): string | null {
  const m = refId.match(
    /^agent-([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})$/,
  );
  return m ? m[1] : null;
}

/** One live agent conversation. The refId is `agent-<uuid>` (a named agent),
 *  a stored sessionId from a deep link, or `new-<nonce>` (the server mints the
 *  session on turn 1). A chat agent's conversation is its persistent session;
 *  a scheduled agent's is the runs feed. No config surface — this view is for
 *  talking to the Stash, nothing else. */
export default function AgentChatView({
  refId,
  onSessionMinted,
}: {
  refId: string;
  /** Fires when the server mints a session for a fresh chat, so the host can
   *  sync its URL / history list to the now-real conversation. */
  onSessionMinted?: (id: string) => void;
}) {
  const isNew = refId.startsWith("new");
  const agentId = agentIdFromRef(refId);
  const [sessionId, setSessionId] = useState<string | null>(isNew ? null : refId);
  // A skill launched into this view: taken once, so reopening it shows the
  // conversation rather than running the skill again.
  const [openingMessage] = useState(() => takeSkillRun(refId));
  const [agent, setAgent] = useState<Agent | null>(null);
  useEffect(() => {
    if (agentId) getAgent(agentId).then(setAgent).catch(() => {});
  }, [agentId]);

  // A named agent's body waits for the agent row — rendering the chat first
  // would flash an empty conversation before a scheduled agent's runs load.
  if (agentId && agent === null) return null;
  const scheduled = agent !== null && (agent.run_mode === "scheduled" || agent.is_curator);
  return (
    <div className="mx-auto flex h-full w-full max-w-3xl flex-col">
      {scheduled && agentId ? (
        <AgentRunsView agentId={agentId} />
      ) : (
        <ChatPanel
          sessionId={sessionId}
          onSessionId={(id) => {
            setSessionId(id);
            onSessionMinted?.(id);
          }}
          agentId={agentId}
          openingMessage={openingMessage}
        />
      )}
    </div>
  );
}
