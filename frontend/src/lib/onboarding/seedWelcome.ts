// Pure utility: pull workspace state, generate the welcome HTML, and PATCH it
// onto workspace.description if the description is still empty. Safe to call
// multiple times — the empty-check keeps it idempotent against the live
// description.

import { isBlankDescription } from "@/components/DescriptionEditor";
import {
  getWorkspace,
  getWorkspaceOverview,
  updateWorkspace,
} from "@/lib/api";
import { generateWelcomeHtml } from "@/lib/onboarding/welcomeContent";

export async function seedWelcomePage(args: {
  workspaceId: string;
  displayName: string;
}): Promise<void> {
  const { workspaceId, displayName } = args;

  const [workspace, overview] = await Promise.all([
    getWorkspace(workspaceId),
    getWorkspaceOverview(workspaceId),
  ]);

  if (!isBlankDescription(workspace.description ?? "")) return;

  const inviteLink =
    typeof window !== "undefined" && workspace.invite_code
      ? `${window.location.origin}/join/${workspace.invite_code}`
      : null;

  const html = generateWelcomeHtml({
    displayName,
    inviteLink,
    counts: {
      pages: overview.files?.pages?.length ?? 0,
      files: overview.files?.files?.length ?? 0,
      sessions: overview.sessions?.length ?? 0,
    },
  });

  await updateWorkspace(workspaceId, { description: html });
}
