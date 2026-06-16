// Given the already-loaded workspace, generate the welcome HTML and PATCH it
// onto workspace.description when the description is still empty. Returns the
// resulting workspace (the PATCH response when seeded, otherwise the input) so
// the caller never has to re-fetch. Idempotent: the empty-check keeps repeat
// calls safe against the live description.

import { isBlankDescription } from "@/components/DescriptionEditor";
import { updateWorkspace } from "@/lib/api";
import { generateWelcomeHtml } from "@/lib/onboarding/welcomeContent";
import type { Workspace } from "@/lib/types";

export async function seedWelcomePage(args: {
  workspace: Workspace;
  displayName: string;
}): Promise<Workspace> {
  const { workspace, displayName } = args;

  if (!isBlankDescription(workspace.description ?? "")) return workspace;

  const inviteLink =
    typeof window !== "undefined" && workspace.invite_code
      ? `${window.location.origin}/join/${workspace.invite_code}`
      : null;

  const html = generateWelcomeHtml({ displayName, inviteLink });
  return updateWorkspace(workspace.id, { description: html });
}
