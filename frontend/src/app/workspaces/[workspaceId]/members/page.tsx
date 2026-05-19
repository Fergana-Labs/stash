"use client";

import { useParams } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import { useBreadcrumbs } from "../../../../components/BreadcrumbContext";
import { WorkspaceSettingsSkeleton } from "../../../../components/SkeletonStates";
import WorkspaceMembersPanel from "../../../../components/workspace/WorkspaceMembersPanel";
import { useAuth } from "../../../../hooks/useAuth";
import { getWorkspace, getWorkspaceMembers } from "../../../../lib/api";
import type { Workspace, WorkspaceMember } from "../../../../lib/types";

export default function WorkspaceMembersPage() {
  const params = useParams();
  const workspaceId = params.workspaceId as string;
  const { user } = useAuth();

  const [workspace, setWorkspace] = useState<Workspace | null>(null);
  const [members, setMembers] = useState<WorkspaceMember[]>([]);
  const [error, setError] = useState("");

  useBreadcrumbs([{ label: "Members" }], `${workspaceId}/members`);

  const load = useCallback(async () => {
    const [nextWorkspace, nextMembers] = await Promise.all([
      getWorkspace(workspaceId),
      getWorkspaceMembers(workspaceId),
    ]);
    setWorkspace(nextWorkspace);
    setMembers(nextMembers);
    setError("");
  }, [workspaceId]);

  useEffect(() => {
    if (!user) return;
    load().catch((e) => {
      setError(e instanceof Error ? e.message : "Failed to load members");
    });
  }, [user, load]);

  if (!user) return null;
  if (!workspace) {
    if (error) return <div className="mx-auto max-w-2xl px-8 py-12 text-muted">{error}</div>;
    return <WorkspaceSettingsSkeleton />;
  }

  const myRole = members.find((member) => member.user_id === user.id)?.role;
  const canManage = myRole === "owner";

  return (
    <div className="scroll-thin flex-1 overflow-y-auto">
      <div className="mx-auto max-w-2xl px-8 py-10">
        <h1 className="font-display text-[28px] font-bold tracking-tight text-foreground">
          Members
        </h1>
        <p className="mt-1 text-[13px] text-muted">{workspace.name}</p>

        {error && (
          <div className="mt-4 rounded-lg border border-red-300/40 bg-red-500/10 px-4 py-2 text-[13px] text-red-500">
            {error}
          </div>
        )}

        <div className="mt-6">
          <WorkspaceMembersPanel
            workspaceId={workspaceId}
            members={members}
            currentUserId={user.id}
            canManage={canManage}
            onReload={load}
          />
        </div>
      </div>
    </div>
  );
}
