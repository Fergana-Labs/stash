// Pure utility: pull workspace state + onboarding state from URL / localStorage,
// generate the welcome HTML, and PATCH it onto workspace.description if the
// description is still empty. Safe to call multiple times — the empty-check
// keeps it idempotent against the live description.

import { isBlankDescription } from "@/components/DescriptionEditor";
import {
  getWorkspace,
  getWorkspaceOverview,
  updateWorkspace,
} from "@/lib/api";
import { generateWelcomeHtml } from "@/lib/onboarding/welcomeContent";
import type { MigrantSource, PathId } from "@/lib/onboarding/paths";

const SHARED_URL_KEY = "stash_onboarding_shared_url";

// Must match page.tsx's pathStorageKey().
function pathStorageKey(userId: string): string {
  return `stash_onboarding_path:${userId}`;
}

export async function seedWelcomePage(args: {
  workspaceId: string;
  userId: string;
  displayName: string;
}): Promise<void> {
  const { workspaceId, userId, displayName } = args;

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
    path: readPath(userId),
    source: readSource(),
    displayName,
    inviteLink,
    sharedUrl: readSharedUrl(),
    counts: {
      pages: overview.files?.pages?.length ?? 0,
      files: overview.files?.files?.length ?? 0,
      sessions: overview.sessions?.length ?? 0,
    },
  });

  await updateWorkspace(workspaceId, { description: html });
  if (typeof window !== "undefined") {
    window.localStorage.removeItem(SHARED_URL_KEY);
  }
}

function readPath(userId: string): PathId | null {
  if (typeof window === "undefined") return null;
  const v = window.localStorage.getItem(pathStorageKey(userId));
  if (v === "migrant" || v === "memory" || v === "sharing") return v;
  return null;
}

function readSource(): MigrantSource | null {
  if (typeof window === "undefined") return null;
  const params = new URLSearchParams(window.location.search);
  const v = params.get("source");
  if (v === "notion" || v === "obsidian" || v === "github" || v === "drive") {
    return v;
  }
  return null;
}

function readSharedUrl(): string | null {
  if (typeof window === "undefined") return null;
  return window.localStorage.getItem(SHARED_URL_KEY);
}
