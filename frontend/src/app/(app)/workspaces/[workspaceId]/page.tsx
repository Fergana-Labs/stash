"use client";

import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import DescriptionEditor, {
  isBlankDescription,
} from "../../../../components/DescriptionEditor";
import { seedWelcomePage } from "../../../../lib/onboarding/seedWelcome";
import { WorkspaceHomeSkeleton } from "../../../../components/SkeletonStates";
import { WorkspaceIcon } from "../../../../components/SkillIcons";
import { useAuth } from "../../../../hooks/useAuth";
import {
  createPage,
  getWorkspace,
  joinWorkspace,
  updateWorkspace,
} from "../../../../lib/api";
import type { Workspace } from "../../../../lib/types";
import { refreshWorkspaceSidebar } from "../../../../lib/skillNavigationCache";

function relativeTime(iso: string): string {
  const ms = Date.now() - new Date(iso).getTime();
  if (ms < 60_000) return "just now";
  const m = Math.floor(ms / 60_000);
  if (m < 60) return `${m} min ago`;
  const h = Math.floor(m / 60);
  if (h < 24) return `${h} h ago`;
  const d = Math.floor(h / 24);
  if (d < 30) return `${d} d ago`;
  return new Date(iso).toLocaleDateString();
}

export default function WorkspaceHomePage() {
  const params = useParams();
  const router = useRouter();
  const workspaceId = params.workspaceId as string;
  const { user, loading } = useAuth();

  const [workspace, setWorkspace] = useState<Workspace | null>(null);
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    try {
      setWorkspace(await getWorkspace(workspaceId));
    } catch {
      setError("Workspace not found");
    }
  }, [workspaceId]);

  useEffect(() => {
    if (!user) return;
    load();
  }, [user, load]);

  useEffect(() => {
    if (!loading && !user) router.push("/login");
  }, [user, loading, router]);

  // Single-owner workspace: the viewer owns their own space.
  const isMember = !!user && !!workspace && workspace.creator_id === user.id;

  // A fresh workspace lands empty; seed the "what to do next" welcome doc as
  // the default description (idempotent — only writes when still blank). Covers
  // skipped onboarding and pre-existing empty workspaces, not just the finish
  // path. The owner can edit or delete it like any page.
  useEffect(() => {
    if (!user || !workspace) return;
    if (workspace.creator_id !== user.id) return;
    if (!isBlankDescription(workspace.description ?? "")) return;
    seedWelcomePage({
      workspaceId,
      displayName: user.display_name || user.name,
    })
      .then(() => getWorkspace(workspaceId))
      .then(setWorkspace)
      .catch(() => {});
  }, [user, workspace, workspaceId]);

  async function handleNewPage() {
    try {
      const page = await createPage(workspaceId, "Untitled");
      refreshWorkspaceSidebar(workspaceId).catch(() => {});
      router.push(`/p/${page.id}`);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to create page");
    }
  }

  async function handleJoin() {
    if (!workspace) return;
    try {
      await joinWorkspace(workspace.invite_code);
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to join");
    }
  }

  if (loading) return <WorkspaceHomeSkeleton />;
  if (!user) return null;
  if (!workspace && !error) return <WorkspaceHomeSkeleton />;

  return (
    <div className="scroll-thin flex-1 overflow-y-auto">
      {/* Cover banner — workspace-customized image, color gradient, or default brand gradient */}
      <div
        className="h-[72px] w-full bg-gradient-to-r from-[var(--color-brand-200)] via-amber-100 to-rose-100 bg-cover bg-center"
        style={
          workspace?.cover_image_url
            ? { backgroundImage: `url(${workspace.cover_image_url})` }
            : workspace?.color_gradient
              ? { backgroundImage: workspace.color_gradient }
              : undefined
        }
      />

      <div className="mx-auto max-w-[920px] px-12 pb-20">
        {/* Identity strip: icon + name + members preview + meta + actions */}
        <div className="flex items-start justify-between gap-3 pt-4">
          <div className="flex min-w-0 items-center gap-3">
            <span className="-mt-9 flex h-12 w-12 flex-shrink-0 items-center justify-center overflow-hidden rounded-[10px] border-2 border-base bg-base text-[28px] text-[var(--color-brand-700)] shadow-sm">
              {workspace?.icon_url ? (
                // eslint-disable-next-line @next/next/no-img-element
                <img
                  src={workspace.icon_url}
                  alt=""
                  className="h-full w-full object-cover"
                />
              ) : (
                <WorkspaceIcon />
              )}
            </span>
            <div className="min-w-0">
              <h2 className="m-0 truncate font-display text-[20px] font-bold leading-tight tracking-[-0.015em] text-foreground">
                {workspace?.name || "Workspace"}
              </h2>
              <div className="mt-1 flex flex-wrap items-center gap-2 text-[12px] text-muted">
                {workspace?.updated_at && (
                  <>
                    <span className="text-muted/60">·</span>
                    <span>updated {relativeTime(workspace.updated_at)}</span>
                  </>
                )}
              </div>
            </div>
          </div>
          <div className="flex flex-shrink-0 items-center gap-1.5 pt-1">
            {isMember && (
              <button
                type="button"
                onClick={handleNewPage}
                className="rounded-md border border-border-subtle bg-raised px-2.5 py-1 text-[12px] font-medium text-foreground hover:bg-raised-2"
              >
                + New page
              </button>
            )}
            {isMember && (
              <Link
                href={`/workspaces/${workspaceId}/settings`}
                title="Workspace settings"
                aria-label="Workspace settings"
                className="inline-flex h-7 w-7 items-center justify-center rounded-md text-muted hover:bg-raised hover:text-foreground"
              >
                <SettingsGlyph />
              </Link>
            )}
          </div>
        </div>

        {error && (
          <div className="mt-4 rounded-lg border border-red-300/40 bg-red-500/10 px-4 py-2 text-[13px] text-red-500">
            {error}
          </div>
        )}

        {!isMember && workspace && (
          <div className="mt-4 flex items-center justify-between rounded-lg border border-border bg-surface px-4 py-3 text-[13px]">
            <span className="text-muted">
              You aren&apos;t a member of this workspace.
            </span>
            <button
              onClick={handleJoin}
              className="rounded-md bg-[var(--color-brand-600)] px-3 py-1.5 text-[12px] font-medium text-white hover:bg-[var(--color-brand-700)]"
            >
              Join workspace
            </button>
          </div>
        )}

        <WorkspaceDescriptionEditor
          workspace={workspace}
          canEdit={isMember}
          onSaved={(updated) => setWorkspace(updated)}
        />

      </div>
    </div>
  );
}

function SettingsGlyph() {
  return (
    <svg
      width="14"
      height="14"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.8"
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      <circle cx="12" cy="12" r="3" />
      <path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 1 1-4 0v-.09a1.65 1.65 0 0 0-1-1.51 1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 1 1-2.83-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 1 1 0-4h.09a1.65 1.65 0 0 0 1.51-1 1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 1 1 2.83-2.83l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 1 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 1 1 2.83 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 1 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z" />
    </svg>
  );
}


function WorkspaceDescriptionEditor({
  workspace,
  canEdit,
  onSaved,
}: {
  workspace: Workspace | null;
  canEdit: boolean;
  onSaved: (updated: Workspace) => void;
}) {
  const description = workspace?.description ?? "";

  if (!workspace) return null;
  if (!canEdit && isBlankDescription(description)) return null;

  return (
    <section className="mt-5">
      <DescriptionEditor
        value={description}
        canEdit={canEdit}
        placeholder="Describe this workspace…"
        ariaLabel="Workspace description"
        workspaceId={workspace.id}
        onSave={async (html) => {
          const updated = await updateWorkspace(workspace.id, {
            description: html,
          });
          onSaved(updated);
        }}
      />
    </section>
  );
}

