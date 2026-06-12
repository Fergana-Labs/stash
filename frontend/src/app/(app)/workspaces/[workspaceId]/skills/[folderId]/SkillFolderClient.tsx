"use client";

import { useParams, useRouter } from "next/navigation";
import { useCallback, useEffect, useMemo, useState } from "react";
import { useBreadcrumbs } from "../../../../../../components/BreadcrumbContext";
import { useShareAction } from "../../../../../../components/ShellChromeContext";
import { FileBrowserSkeleton } from "../../../../../../components/SkeletonStates";
import ResourceShareButton from "../../../../../../components/share/ResourceShareButton";
import SkillShareButton from "../../../../../../components/skill/SkillShareButton";
import WorkspaceFileBrowser from "../../../../../../components/workspace/file-browser/WorkspaceFileBrowser";
import { useAuth } from "../../../../../../hooks/useAuth";
import {
  getFolderContents,
  listSkills,
  trashItem,
  type FolderContents,
  type SkillPublishInfo,
} from "../../../../../../lib/api";
import { SKILL_MD } from "../../../../../../lib/localSkill";
import { refreshWorkspaceSidebar } from "../../../../../../lib/skillNavigationCache";

// Browse a skill folder (or a subfolder inside one). Same file browser as
// the Files routes, but folder links stay on the skill browse route and the
// action bar carries skill-specific actions (Share, Convert to folder).
export default function SkillFolderClient() {
  const params = useParams();
  const router = useRouter();
  const workspaceId = params.workspaceId as string;
  const folderId = params.folderId as string;
  const { user, loading } = useAuth();

  const [contents, setContents] = useState<FolderContents | null>(null);
  const [publish, setPublish] = useState<SkillPublishInfo | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    if (!loading && !user) router.push("/login");
  }, [user, loading, router]);

  useEffect(() => {
    if (!user) return;
    let cancelled = false;
    setContents(null);
    getFolderContents(workspaceId, folderId)
      .then((c) => {
        if (cancelled) return;
        // A non-skill folder doesn't belong on this route — bounce to Files.
        if (!c.folder.is_skill && !c.breadcrumbs.some((b) => b.is_skill)) {
          router.replace(`/workspaces/${workspaceId}/folders/${folderId}`);
          return;
        }
        setContents(c);
      })
      .catch((e) => {
        if (!cancelled) setError(e instanceof Error ? e.message : "Failed to load skill");
      });
    return () => {
      cancelled = true;
    };
  }, [user, workspaceId, folderId, router]);

  // The skill root is the first is_skill breadcrumb; the publish record
  // (when minted) lives on that folder.
  const skillRootId = useMemo(
    () => contents?.breadcrumbs.find((b) => b.is_skill)?.id ?? null,
    [contents],
  );

  useEffect(() => {
    if (!user || !skillRootId) return;
    let cancelled = false;
    listSkills(workspaceId)
      .then((skills) => {
        if (cancelled) return;
        setPublish(skills.find((s) => s.folder_id === skillRootId)?.published ?? null);
      })
      .catch(() => {});
    return () => {
      cancelled = true;
    };
  }, [user, workspaceId, skillRootId]);

  const crumbs = useMemo(() => {
    if (!contents) return [{ label: "Skills", href: `/workspaces/${workspaceId}/skills` }];
    const firstSkillIndex = contents.breadcrumbs.findIndex((b) => b.is_skill);
    const trail = contents.breadcrumbs
      .slice(firstSkillIndex === -1 ? 0 : firstSkillIndex, -1)
      .map((cr) => ({
        label: cr.name,
        href: `/workspaces/${workspaceId}/skills/${cr.id}`,
      }));
    return [
      { label: "Skills", href: `/workspaces/${workspaceId}/skills` },
      ...trail,
      { label: contents.folder.name },
    ];
  }, [contents, workspaceId]);

  useBreadcrumbs(
    crumbs,
    `${workspaceId}/skills/${folderId}/${crumbs.map((c) => c.label).join("/")}`
  );

  const convertToFolder = useCallback(async () => {
    if (!contents) return;
    const publishedWarning = publish
      ? " Its share link will stop working."
      : "";
    const yes = window.confirm(
      `Convert "${contents.folder.name}" back to a plain folder? This deletes its SKILL.md.${publishedWarning}`,
    );
    if (!yes) return;
    const skillMd = contents.pages.find((p) => p.name === SKILL_MD);
    if (!skillMd) {
      setError("SKILL.md not found in this folder.");
      return;
    }
    try {
      await trashItem(workspaceId, "page", skillMd.id);
      await refreshWorkspaceSidebar(workspaceId).catch(() => {});
      router.push(`/workspaces/${workspaceId}/folders/${folderId}`);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Convert failed");
    }
  }, [contents, publish, workspaceId, folderId, router]);

  // Skill actions live on the skill root; subfolders are plain browsing.
  const isSkillRoot = !!contents?.folder.is_skill;
  const folderName = contents?.folder.name ?? "";
  const shareAction = useMemo(() => {
    if (!user || !isSkillRoot) return null;
    return (
      <div className="flex items-center gap-1.5">
        <button
          type="button"
          onClick={() => void convertToFolder()}
          className="rounded-md bg-surface px-2.5 py-1 text-[12.5px] font-medium text-dim ring-1 ring-inset ring-border hover:bg-raised hover:text-foreground"
        >
          Convert to folder
        </button>
        {/* Person-to-person sharing of a skill = sharing its folder. */}
        <ResourceShareButton
          objectType="folder"
          objectId={folderId}
          resourceName={folderName}
          resourceUrlPath={`/workspaces/${workspaceId}/skills/${folderId}`}
          currentUser={user}
        />
        <SkillShareButton
          workspaceId={workspaceId}
          folderId={folderId}
          publish={publish}
          onPublishChange={setPublish}
        />
      </div>
    );
  }, [user, isSkillRoot, workspaceId, folderId, folderName, publish, convertToFolder]);
  useShareAction(shareAction);

  if (loading) return <FileBrowserSkeleton />;
  if (!user) return null;
  if (error) {
    return (
      <div className="mx-auto max-w-md py-24 text-center">
        <h1 className="font-display text-[24px] font-bold text-foreground">Skill unavailable</h1>
        <p className="mt-2 text-[14px] leading-relaxed text-dim">{error}</p>
      </div>
    );
  }
  if (!contents) return <FileBrowserSkeleton />;

  return (
    <WorkspaceFileBrowser
      workspaceId={workspaceId}
      folderId={folderId}
      folderHrefBase={`/workspaces/${workspaceId}/skills`}
    />
  );
}
