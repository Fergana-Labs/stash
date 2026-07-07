"use client";

import { useRouter } from "next/navigation";
import { useCallback, useEffect, useMemo, useState } from "react";
import { useBreadcrumbs } from "@/components/BreadcrumbContext";
import { useConfirm } from "@/components/ConfirmDialog";
import { useShareAction } from "@/components/ShellChromeContext";
import { FileBrowserSkeleton } from "@/components/SkeletonStates";
import ResourceShareButton from "@/components/share/ResourceShareButton";
import SkillShareButton from "@/components/skill/SkillShareButton";
import FileBrowser from "@/components/content/file-browser/FileBrowser";
import { useAuth } from "@/hooks/useAuth";
import {
  deleteSkillRecord,
  getFolderContents,
  listSkills,
  type FolderContents,
  type SkillRecordInfo,
} from "@/lib/api";
import { refreshSidebar } from "@/lib/skillNavigationCache";

// Browse a skill folder (or a subfolder inside one). Same file browser as
// the Files routes, but folder links stay on the skill browse route and the
// action bar carries skill-specific actions (Share, Convert to folder).
export default function SkillFolderClient({ folderId }: { folderId: string }) {
  const router = useRouter();
  const { user, loading } = useAuth();
  const confirm = useConfirm();

  const [contents, setContents] = useState<FolderContents | null>(null);
  const [skillRecord, setSkillRecord] = useState<SkillRecordInfo | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    if (!loading && !user) router.push("/login");
  }, [user, loading, router]);

  useEffect(() => {
    if (!user) return;
    let cancelled = false;
    setContents(null);
    getFolderContents(folderId)
      .then((c) => {
        if (cancelled) return;
        // A non-skill folder doesn't belong on this route — bounce to Files.
        if (!c.folder.is_skill && !c.breadcrumbs.some((b) => b.is_skill)) {
          router.replace(`/folders/${folderId}`);
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
  }, [user, folderId, router]);

  // The skill root is the first is_skill breadcrumb; the skill record
  // (always present for a skill folder) lives on that folder.
  const skillRootId = useMemo(
    () => contents?.breadcrumbs.find((b) => b.is_skill)?.id ?? null,
    [contents],
  );

  useEffect(() => {
    if (!user || !skillRootId) return;
    let cancelled = false;
    listSkills()
      .then((skills) => {
        if (cancelled) return;
        setSkillRecord(skills.find((s) => s.folder_id === skillRootId)?.skill ?? null);
      })
      .catch(() => {});
    return () => {
      cancelled = true;
    };
  }, [user, skillRootId]);

  const crumbs = useMemo(() => {
    if (!contents) return [{ label: "Skills", href: `/skills` }];
    const firstSkillIndex = contents.breadcrumbs.findIndex((b) => b.is_skill);
    const trail = contents.breadcrumbs
      .slice(firstSkillIndex === -1 ? 0 : firstSkillIndex, -1)
      .map((cr) => ({
        label: cr.name,
        href: `/skills/${cr.id}`,
      }));
    return [
      { label: "Skills", href: `/skills` },
      ...trail,
      { label: contents.folder.name },
    ];
  }, [contents]);

  useBreadcrumbs(
    crumbs,
    `skills/${folderId}/${crumbs.map((c) => c.label).join("/")}`
  );

  // Declassify: delete the skill record. Files (including SKILL.md) and any
  // shares on the folder stay untouched.
  const convertToFolder = useCallback(async () => {
    if (!contents || !user) return;
    if (!skillRecord) {
      setError("Skill record not loaded yet.");
      return;
    }
    const yes = await confirm({
      title: `Convert "${contents.folder.name}" back to a plain folder?`,
      body: "It moves back to your Files. Its files stay untouched.",
      confirmLabel: "Convert",
    });
    if (!yes) return;
    try {
      await deleteSkillRecord(skillRecord.id);
      await refreshSidebar().catch(() => {});
      router.push(`/folders/${folderId}`);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Convert failed");
    }
  }, [contents, skillRecord, user, folderId, router, confirm]);

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
          className="cursor-pointer rounded-md bg-surface px-2.5 py-1 text-[12.5px] font-medium text-dim ring-1 ring-inset ring-border hover:bg-raised hover:text-foreground"
        >
          Convert to folder
        </button>
        {/* Person-to-person sharing of a skill = sharing its folder. */}
        <ResourceShareButton
          objectType="folder"
          objectId={folderId}
          resourceName={folderName}
          resourceUrlPath={`/skills/${folderId}`}
          currentUser={user}
        />
        {skillRecord && (
          <SkillShareButton
            folderId={folderId}
            skill={skillRecord}
            onSkillChange={setSkillRecord}
          />
        )}
      </div>
    );
  }, [user, isSkillRoot, folderId, folderName, skillRecord, convertToFolder]);
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
    <FileBrowser
      folderId={folderId}
      folderHrefBase={`/skills`}
    />
  );
}
