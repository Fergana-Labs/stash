"use client";

import PageClient from "@/app/(app)/p/[pageId]/PageClient";
import FileClient from "@/app/(app)/f/[fileId]/FileClient";
import TableClient from "@/app/(app)/tables/[tableId]/TableClient";
import SessionsPage from "@/app/(app)/sessions/page";
import SessionClient from "@/app/(app)/sessions/[sessionId]/SessionClient";
import SkillFolderClient from "@/app/(app)/skills/folder/[folderId]/SkillFolderClient";
import FolderClient from "@/app/(app)/folders/[folderId]/FolderClient";
import IntegrationsSettings from "@/components/integrations/IntegrationsSettings";
import { IntegrationDetail } from "@/app/(app)/integrations/[provider]/page";
import { connectorForProvider } from "@/components/integrations/connectors";
import MachineFileView from "@/components/workspace/machine-file-view";
import TerminalPanel from "@/components/workspace/TerminalPanel";
import type { WorkbenchTab } from "@/lib/workspace-store";

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
  // The tool body is a plain document flow with no height or scroller of its
  // own, so the tab gives it one.
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
  if (tab.kind === "machine-file") return <MachineFileView path={tab.refId} />;
  if (tab.kind === "terminal")
    return (
      <div className="h-full p-3">
        <TerminalPanel />
      </div>
    );
  return null;
}
