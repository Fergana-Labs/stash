"use client";

import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import DescriptionEditor, {
  isBlankDescription,
} from "../../../components/DescriptionEditor";
import MembersModal from "../../../components/MembersModal";
import { SkeletonBlock, WorkspaceHomeSkeleton } from "../../../components/SkeletonStates";
import StashQuickAdd from "../../../components/StashQuickAdd";
import { WorkspaceIcon } from "../../../components/StashIcons";
import ContributorActivityTimeline from "../../../components/viz/ContributorActivityTimeline";
import EmbeddingSpaceExplorer from "../../../components/viz/EmbeddingSpaceExplorer";
import { useAuth } from "../../../hooks/useAuth";
import {
  getActivityTimeline,
  getEmbeddingProjection,
  getWorkspace,
  getWorkspaceMembers,
  joinWorkspace,
  updateWorkspace,
} from "../../../lib/api";
import type {
  ActivityTimeline,
  EmbeddingProjection,
  Workspace,
  WorkspaceMember,
} from "../../../lib/types";

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
  const [members, setMembers] = useState<WorkspaceMember[]>([]);
  const [timeline, setTimeline] = useState<ActivityTimeline | null>(null);
  const [projection, setProjection] = useState<EmbeddingProjection | null>(
    null,
  );
  const [insightsLoaded, setInsightsLoaded] = useState(false);
  const [error, setError] = useState("");
  const [membersOpen, setMembersOpen] = useState(false);

  const load = useCallback(async () => {
    setInsightsLoaded(false);
    const [w, m, t, p] = await Promise.allSettled([
      getWorkspace(workspaceId),
      getWorkspaceMembers(workspaceId),
      // 365 days because seeded dev data is dated; for production the
      // visualization remains legible at this window (1 row per contributor × 365
      // 14px cells = ~1.4kpx wide, fits with horizontal scroll).
      getActivityTimeline(365, "day", workspaceId),
      getEmbeddingProjection(500, undefined, workspaceId),
    ]);
    if (w.status === "fulfilled") setWorkspace(w.value);
    else setError("Workspace not found");
    if (m.status === "fulfilled") setMembers(m.value);
    if (t.status === "fulfilled") setTimeline(t.value);
    if (p.status === "fulfilled") setProjection(p.value);
    setInsightsLoaded(true);
  }, [workspaceId]);

  useEffect(() => {
    if (!user) return;
    load();
  }, [user, load]);

  useEffect(() => {
    if (!loading && !user) router.push("/login");
  }, [user, loading, router]);

  const isMember = !!user && members.some((m) => m.user_id === user.id);

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
    <>
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
                  <button
                    type="button"
                    onClick={() => setMembersOpen(true)}
                    title="View members"
                    className="inline-flex items-center gap-1 rounded px-1 py-0.5 hover:bg-raised"
                  >
                    <MemberCount members={members} />
                  </button>
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

          {/* Quick-add: paste URL or drop a file. .jsonl files route to
              session-transcript upload; anything else uploads to Files. */}
          {isMember && (
            <section className="mt-6">
              <div className="sys-label mb-1.5">
                Quick add — paste a URL, drop a file, drop a .jsonl transcript
              </div>
              <StashQuickAdd workspaceId={workspaceId} onAdded={load} />
            </section>
          )}

          {/* Visualizations: human/agent session activity + 3D embedding view.
              Section renders even when empty so users see the placeholder
              and know what's coming once data exists. */}
          <section className="mt-8">
            <div className="sys-label mb-1.5">Human / agent commits — past year</div>
            <div className="card-soft overflow-x-auto p-3">
              {!insightsLoaded ? (
                <SkeletonBlock className="h-40 w-full" />
              ) : timeline && timeline.contributors.length > 0 ? (
                <ContributorActivityTimeline data={timeline} />
              ) : (
                <div className="px-2 py-6 text-center text-[12.5px] text-muted">
                  No agent session commits yet. Push a transcript via Quick add
                  or the CLI to populate this view.
                </div>
              )}
            </div>
          </section>

          <section className="mt-6">
            <div className="sys-label mb-1.5">
              Embedding space — workspace knowledge map
            </div>
            <div className="card-soft p-3">
              {!insightsLoaded ? (
                <SkeletonBlock className="h-40 w-full" />
              ) : projection && projection.points.length > 0 ? (
                <EmbeddingSpaceExplorer data={projection} />
              ) : (
                <div className="px-2 py-6 text-center text-[12.5px] text-muted">
                  No embeddings indexed yet. Pages, table rows, and session
                  events get embedded as they&apos;re added.
                </div>
              )}
            </div>
          </section>
        </div>
      </div>
      <MembersModal
        workspaceId={workspaceId}
        open={membersOpen}
        onClose={() => setMembersOpen(false)}
      />
    </>
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

function MemberCount({ members }: { members: WorkspaceMember[] }) {
  if (!members.length) return null;

  const label = `${members.length} member${members.length === 1 ? "" : "s"}`;

  return <span>{label}</span>;
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
        onSave={async (html) => {
          const updated = await updateWorkspace(workspace.id, { description: html });
          onSaved(updated);
        }}
      />
    </section>
  );
}
