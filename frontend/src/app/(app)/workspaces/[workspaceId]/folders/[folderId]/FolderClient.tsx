"use client";

import Link from "next/link";
import { useParams, useRouter, useSearchParams } from "next/navigation";
import { useCallback, useEffect, useMemo, useState } from "react";
import { useBreadcrumbs } from "../../../../../../components/BreadcrumbContext";
import { useShareAction } from "../../../../../../components/ShellChromeContext";
import { FileBrowserSkeleton } from "../../../../../../components/SkeletonStates";
import ResourceShareButton from "../../../../../../components/share/ResourceShareButton";
import WorkspaceFileBrowser from "../../../../../../components/workspace/file-browser/WorkspaceFileBrowser";
import { useAuth } from "../../../../../../hooks/useAuth";
import {
  ApiError,
  getFolderContents,
  getPublicSkill,
  type PublicSkillItem,
  type WorkspaceSkill,
} from "../../../../../../lib/api";
import { FolderBody } from "../../../../skills/[slug]/SkillItemBodies";

export default function FolderDetailPage() {
  const params = useParams();
  const router = useRouter();
  const searchParams = useSearchParams();
  const workspaceId = params.workspaceId as string;
  const folderId = params.folderId as string;
  const { user, loading } = useAuth();
  const skillSlug = searchParams.get("skill");

  // Small auxiliary breadcrumb fetch so the top bar is correct before the
  // file browser shell finishes its own load. The shell still owns the main
  // folder-contents fetch.
  const [crumbs, setCrumbs] = useState<{ label: string; href?: string }[]>([
    { label: "Folder" },
  ]);
  const [folderName, setFolderName] = useState<string | null>(null);
  const [skillFallback, setSkillFallback] = useState<
    { skill: WorkspaceSkill; item: PublicSkillItem } | null
  >(null);
  const [error, setError] = useState("");

  const loadSkillFallback = useCallback(async () => {
    if (!skillSlug) return false;
    try {
      const data = await getPublicSkill(skillSlug);
      const item = data.items.find(
        (it) => it.object_type === "folder" && it.object_id === folderId,
      );
      if (!item) {
        setError("This folder isn't part of the linked Skill.");
        return false;
      }
      setSkillFallback({ skill: data.skill, item });
      setError("");
      return true;
    } catch (e) {
      setError(e instanceof Error ? e.message : "Skill not found");
      return false;
    }
  }, [skillSlug, folderId]);

  useEffect(() => {
    if (!user) {
      if (!loading && skillSlug) void loadSkillFallback();
      return;
    }
    let cancelled = false;
    setFolderName(null);
    getFolderContents(workspaceId, folderId)
      .then((c) => {
        if (cancelled) return;
        const trail = c.breadcrumbs.slice(0, -1).map((cr) => ({
          label: cr.name,
          href: `/workspaces/${workspaceId}/folders/${cr.id}`,
        }));
        setCrumbs([
          { label: "Files", href: `/workspaces/${workspaceId}/files` },
          ...trail,
          { label: c.folder.name },
        ]);
        setFolderName(c.folder.name);
        setSkillFallback(null);
      })
      .catch(async (e) => {
        if (cancelled) return;
        if (
          skillSlug &&
          e instanceof ApiError &&
          (e.status === 401 || e.status === 403 || e.status === 404)
        ) {
          await loadSkillFallback();
        }
      });
    return () => {
      cancelled = true;
    };
  }, [user, loading, workspaceId, folderId, skillSlug, loadSkillFallback]);

  useBreadcrumbs(
    crumbs,
    `${workspaceId}/files/${folderId}/${crumbs.map((c) => c.label).join("/")}`
  );

  const shareAction = useMemo(() => {
    if (!folderName || skillSlug || !user) return null;
    return (
      <ResourceShareButton
        objectType="folder"
        objectId={folderId}
        resourceName={folderName}
        resourceUrlPath={`/workspaces/${workspaceId}/folders/${folderId}`}
        currentUser={user}
      />
    );
  }, [folderId, folderName, skillSlug, user, workspaceId]);
  useShareAction(shareAction);

  useEffect(() => {
    if (!loading && !user && !skillSlug) router.push("/login");
  }, [user, loading, router, skillSlug]);

  if (loading) return <FileBrowserSkeleton />;
  if (skillFallback) {
    return (
      <SkillFallbackFolderView
        skillSlug={skillSlug ?? ""}
        skillTitle={skillFallback.skill.title}
        item={skillFallback.item}
      />
    );
  }
  if (!user) {
    if (!skillSlug) return null;
    if (!error) return <FileBrowserSkeleton />;
    return (
      <div className="mx-auto max-w-md py-24 text-center">
        <h1 className="font-display text-[24px] font-bold text-foreground">Folder unavailable</h1>
        <p className="mt-2 text-[14px] leading-relaxed text-dim">{error}</p>
      </div>
    );
  }

  return <WorkspaceFileBrowser workspaceId={workspaceId} folderId={folderId} />;
}

function SkillFallbackFolderView({
  skillSlug,
  skillTitle,
  item,
}: {
  skillSlug: string;
  skillTitle: string;
  item: PublicSkillItem;
}) {
  return (
    <div className="scroll-thin flex-1 overflow-y-auto">
      <div className="mx-auto max-w-[920px] px-12 pb-20 pt-6">
        <Link
          href={`/skills/${skillSlug}`}
          className="inline-flex items-center gap-1 text-[12.5px] text-muted hover:text-foreground"
        >
          ← {skillTitle}
        </Link>
        <h1 className="mt-3 m-0 font-display text-[22px] font-bold leading-tight tracking-[-0.015em] text-foreground">
          {item.label || "(untitled folder)"}
        </h1>
        <div className="mt-1 text-[11.5px] uppercase tracking-wide text-muted">
          folder · read-only via Skill
        </div>
        <div className="mt-6">
          <FolderBody item={item} />
        </div>
      </div>
    </div>
  );
}
