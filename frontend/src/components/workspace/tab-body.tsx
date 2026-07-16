"use client";

import { useState } from "react";
import PageClient from "@/app/(app)/p/[pageId]/PageClient";
import FileClient from "@/app/(app)/f/[fileId]/FileClient";
import TableClient from "@/app/tables/[tableId]/TableClient";
import SessionsPage from "@/app/(app)/sessions/page";
import SessionClient from "@/app/(app)/sessions/[sessionId]/SessionClient";
import SkillFolderClient from "@/app/(app)/skills/folder/[folderId]/SkillFolderClient";
import FolderClient from "@/app/(app)/folders/[folderId]/FolderClient";
import ChatPanel from "@/components/agents/ChatPanel";
import IntegrationsSettings from "@/components/integrations/IntegrationsSettings";
import { IntegrationDetail } from "@/app/(app)/integrations/[provider]/page";
import { connectorForProvider } from "@/components/integrations/connectors";
import MachineFileView from "@/components/workspace/machine-file-view";
import TerminalPanel from "@/components/agents/TerminalPanel";
import AgentConfigPanel from "@/components/agents/AgentConfigPanel";
import { takeAgentConfigView } from "@/lib/agent-tab-view";
import type { WorkbenchTab } from "@/lib/workspace-store";

/** The agentId an agent tab's refId points at, when it encodes one: a per-agent
 *  chat (`agent-<id>`) or a fresh chat (`new:<id>:<nonce>`). A raw session id
 *  from a recent chat doesn't, so those tabs are chat-only. */
function agentIdFromRef(refId: string): string | null {
  if (refId.startsWith("new:")) return refId.split(":")[1] || null;
  if (refId.startsWith("agent-")) return refId.slice("agent-".length) || null;
  return null;
}

function AgentViewSelector({
  view,
  onChange,
}: {
  view: "chat" | "config";
  onChange: (v: "chat" | "config") => void;
}) {
  return (
    <div className="flex shrink-0 justify-center border-b border-border px-4 py-2">
      <div className="inline-flex gap-1 rounded-full border border-border bg-surface/60 p-1 shadow-sm">
        {(["chat", "config"] as const).map((key) => {
          const active = view === key;
          return (
            <button
              key={key}
              type="button"
              onClick={() => onChange(key)}
              className={
                "cursor-pointer rounded-full px-3 py-1 text-[12px] leading-none transition-colors " +
                (active
                  ? "bg-base font-semibold text-foreground shadow-sm"
                  : "text-muted-foreground hover:bg-raised/70 hover:text-foreground")
              }
            >
              {key === "config" ? "Config" : "Chat"}
            </button>
          );
        })}
      </div>
    </div>
  );
}

/** A live agent tab: chat and config in one tab, switched by a selector. The
 *  refId is a stored sessionId, `agent-<id>` (the per-agent chat), or
 *  `new:<id>:<nonce>` for a fresh chat. The server mints the session on turn 1.
 *  Both panels stay mounted so switching never drops an in-flight stream. */
function AgentChatTab({ refId }: { refId: string }) {
  const isNew = refId.startsWith("new");
  const agentId = agentIdFromRef(refId);
  const [sessionId, setSessionId] = useState<string | null>(isNew ? null : refId);
  const [view, setView] = useState<"chat" | "config">(() =>
    agentId && takeAgentConfigView(agentId) ? "config" : "chat",
  );
  return (
    <div className="mx-auto flex h-full w-full max-w-3xl flex-col">
      {agentId && <AgentViewSelector view={view} onChange={setView} />}
      <div className={view === "chat" ? "flex min-h-0 flex-1 flex-col" : "hidden"}>
        <ChatPanel sessionId={sessionId} onSessionId={setSessionId} agentId={agentId} />
      </div>
      {agentId && (
        <div className={view === "config" ? "min-h-0 flex-1 overflow-y-auto" : "hidden"}>
          <AgentConfigPanel agentId={agentId} />
        </div>
      )}
    </div>
  );
}

/** Renders a tab's content by (kind, refId). Each kind reuses the same client
 *  its permanent route renders, so a tab and a deep link show identical content.
 *  The workbench is decoupled from the rail/explorer — any section's items open
 *  here as tabs. */
export default function TabBody({ tab }: { tab: WorkbenchTab }) {
  if (tab.kind === "page") return <PageClient pageId={tab.refId} />;
  if (tab.kind === "file") return <FileClient fileId={tab.refId} />;
  if (tab.kind === "table") return <TableClient tableId={tab.refId} embedded />;
  if (tab.kind === "sessions-home") return <SessionsPage />;
  if (tab.kind === "session") return <SessionClient sessionId={tab.refId} />;
  if (tab.kind === "skill") return <SkillFolderClient folderId={tab.refId} />;
  if (tab.kind === "folder") return <FolderClient folderId={tab.refId} />;
  if (tab.kind === "agent") return <AgentChatTab refId={tab.refId} />;
  // Tool + agent-config bodies are plain document flows with no height or
  // scroller of their own, so the tab gives them one (same as AgentChatTab
  // does for the config side of a chat tab).
  if (tab.kind === "tool")
    return (
      <div className="min-h-0 flex-1 overflow-y-auto">
        {/* refId is a provider slug (clicked a specific tool) → its detail;
            the legacy "integrations" refId shows the whole list. */}
        {connectorForProvider(tab.refId) ? (
          <IntegrationDetail provider={tab.refId} />
        ) : (
          <div className="mx-auto w-full max-w-3xl px-6 py-6">
            <IntegrationsSettings embedded />
          </div>
        )}
      </div>
    );
  if (tab.kind === "agent-config")
    return (
      <div className="min-h-0 flex-1 overflow-y-auto">
        <AgentConfigPanel agentId={tab.refId} />
      </div>
    );
  if (tab.kind === "machine-file") return <MachineFileView path={tab.refId} />;
  if (tab.kind === "terminal")
    return (
      <div className="h-full p-3">
        <TerminalPanel />
      </div>
    );
  return null;
}
