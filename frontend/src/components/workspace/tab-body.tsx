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
import MachineFileView from "@/components/workspace/machine-file-view";
import TerminalPanel from "@/components/agents/TerminalPanel";
import AgentConfigPanel from "@/components/agents/AgentConfigPanel";
import type { WorkbenchTab } from "@/lib/workspace-store";

/** A live agent chat tab. The refId is either a stored sessionId, or
 *  `new:<agentId>:<nonce>` for a fresh chat under a specific agent (agentId
 *  may be empty → default agent). The server mints the session on turn 1. */
function AgentChatTab({ refId }: { refId: string }) {
  const isNew = refId.startsWith("new");
  const agentId = isNew && refId.startsWith("new:") ? refId.split(":")[1] || null : null;
  const [sessionId, setSessionId] = useState<string | null>(isNew ? null : refId);
  return (
    <div className="mx-auto flex h-full w-full max-w-3xl flex-col">
      <ChatPanel sessionId={sessionId} onSessionId={setSessionId} agentId={agentId} />
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
  if (tab.kind === "tool")
    return (
      <div className="mx-auto w-full max-w-3xl px-6 py-6">
        <IntegrationsSettings embedded />
      </div>
    );
  if (tab.kind === "agent-config") return <AgentConfigPanel agentId={tab.refId} />;
  if (tab.kind === "machine-file") return <MachineFileView path={tab.refId} />;
  if (tab.kind === "terminal")
    return (
      <div className="h-full p-3">
        <TerminalPanel />
      </div>
    );
  return null;
}
