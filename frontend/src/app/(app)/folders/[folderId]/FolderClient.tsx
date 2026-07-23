"use client";

import Link from "next/link";
import { useParams, useRouter, useSearchParams } from "next/navigation";
import { useCallback, useEffect, useMemo, useState } from "react";
import { useBreadcrumbs } from "@/components/BreadcrumbContext";
import { useShareAction } from "@/components/ShellChromeContext";
import { FileBrowserSkeleton } from "@/components/SkeletonStates";
import ResourceShareButton from "@/components/share/ResourceShareButton";
import FileBrowser from "@/components/content/file-browser/FileBrowser";
import { useAuth } from "@/hooks/useAuth";
import {
  ApiError,
  createPage,
  getFolderContents,
  getPublicSkill,
  type FolderBreadcrumb,
  type PublicSkillContents,
  type PublicSkillSubfolder,
} from "@/lib/api";
import {
  findInSkillContents,
  SKILL_MD,
  skillMdTemplate,
} from "@/lib/localSkill";
import { sectionCrumbs, useMemoryFolderId } from "@/lib/memory-folder";
import { refreshSidebar } from "@/lib/skillNavigationCache";

export default function FolderDetailPage({ folderId: folderIdProp }: { folderId?: string }) {
  const params = useParams();
  const router = useRouter();
  const searchParams = useSearchParams();
  // Prop wins (workbench tab); otherwise read the route param (deep link).
  const folderId = folderIdProp ?? (params.folderId as string);
  const { user, loading } = useAuth();
  const skillSlug = folderIdProp ? null : searchParams.get("skill");

  // Small auxiliary breadcrumb fetch so the top bar is correct before the
  // file browser shell finishes its own load. The shell still owns the main
  // folder-contents fetch.
  const [chain, setChain] = useState<{
    breadcrumbs: FolderBreadcrumb[];
    name: string;
    id: string;
  } | null>(null);
  const memoryFolderId = useMemoryFolderId();
  const crumbs = useMemo(() => {
    if (!chain) return [{ label: "Folder" }];
    if (chain.id === memoryFolderId) return [{ label: "Memory" }];
    return [
      ...sectionCrumbs(chain.breadcrumbs.slice(0, -1), memoryFolderId),
      { label: chain.name },
    ];
  }, [chain, memoryFolderId]);
  const [folderName, setFolderName] = useState<string | null>(null);
  const [skillFallback, setSkillFallback] = useState<{
    skillSlug: string;
    skillTitle: string;
    folder: PublicSkillSubfolder;
    contents: PublicSkillContents;
  } | null>(null);
  const [error, setError] = useState("");
  const [converting, setConverting] = useState(false);

  const loadSkillFallback = useCallback(async () => {
    if (!skillSlug) return false;
    try {
      const data = await getPublicSkill(skillSlug);
      const folder = findInSkillContents(data.contents, "folder", folderId);
      if (!folder) {
        setError("This folder isn't part of the linked Skill.");
        return false;
      }
      setSkillFallback({
        skillSlug,
        skillTitle: data.skill.title,
        folder,
        contents: data.contents,
      });
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
    setChain(null);
    getFolderContents(folderId)
      .then((c) => {
        if (cancelled) return;
        // Skill folders live on the skill browse route — deep links self-heal.
        if (c.folder.is_skill || c.breadcrumbs.some((b) => b.is_skill)) {
          router.replace(`/skills/${folderId}`);
          return;
        }
        setChain({ breadcrumbs: c.breadcrumbs, name: c.folder.name, id: c.folder.id });
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
  }, [user, loading, folderId, skillSlug, loadSkillFallback, router]);

  useBreadcrumbs(
    crumbs,
    `files/${folderId}/${crumbs.map((c) => c.label).join("/")}`
  );

  const convertToSkill = useCallback(async () => {
    if (!folderName || !user) return;
    setConverting(true);
    try {
      await createPage(SKILL_MD, folderId, skillMdTemplate(folderName));
      await refreshSidebar().catch(() => {});
      router.push(`/skills/${folderId}`);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Convert failed");
    } finally {
      setConverting(false);
    }
  }, [folderName, user, folderId, router]);

  const shareAction = useMemo(() => {
    if (!folderName || skillSlug || !user) return null;
    return (
      <div className="flex items-center gap-1.5">
        <button
          type="button"
          onClick={() => void convertToSkill()}
          disabled={converting}
          className="cursor-pointer rounded-md bg-surface px-2.5 py-1 text-[12.5px] font-medium text-dim ring-1 ring-inset ring-border hover:bg-raised hover:text-foreground disabled:opacity-50"
        >
          {converting ? "Converting…" : "Convert to Skill"}
        </button>
        <ResourceShareButton
          objectType="folder"
          objectId={folderId}
          resourceName={folderName}
          resourceUrlPath={`/folders/${folderId}`}
          currentUser={user}
        />
      </div>
    );
  }, [folderId, folderName, skillSlug, user, convertToSkill, converting]);
  useShareAction(shareAction);

  useEffect(() => {
    if (!loading && !user && !skillSlug) router.push("/login");
  }, [user, loading, router, skillSlug]);

  if (loading) return <FileBrowserSkeleton />;
  if (skillFallback) {
    return <SkillFallbackFolderView {...skillFallback} />;
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

  return <FileBrowser folderId={folderId} />;
}

// Read-only listing of the subfolder's contents, sourced from the public
// skill payload (for viewers who can't reach the owner's endpoint).
function SkillFallbackFolderView({
  skillSlug,
  skillTitle,
  folder,
  contents,
}: {
  skillSlug: string;
  skillTitle: string;
  folder: PublicSkillSubfolder;
  contents: PublicSkillContents;
}) {
  const inFolder = (path: string[]) =>
    path.length >= folder.path.length &&
    folder.path.every((part, i) => path[i] === part);
  const pages = contents.pages.filter((p) => inFolder(p.folder_path));
  const files = contents.files.filter((f) => inFolder(f.folder_path));
  const tables = contents.tables.filter((t) => inFolder(t.folder_path));
  const skill = encodeURIComponent(skillSlug);

  return (
    <div className="scroll-thin flex-1 overflow-y-auto">
      <div className="mx-auto max-w-[920px] px-12 pb-20 pt-6">
        <Link
          href={`/skills/${skillSlug}`}
          className="inline-flex items-center gap-1 text-[12.5px] text-muted-foreground hover:text-foreground"
        >
          ← {skillTitle}
        </Link>
        <h1 className="mt-3 m-0 font-display text-[22px] font-bold leading-tight tracking-[-0.015em] text-foreground">
          {folder.name || "(untitled folder)"}
        </h1>
        <div className="mt-1 text-[11.5px] uppercase tracking-wide text-muted-foreground">
          folder · read-only via Skill
        </div>
        <div className="mt-6 flex flex-col gap-1">
          {pages.map((p) => (
            <FallbackRow key={p.id} href={`/p/${p.id}?skill=${skill}`} name={p.name} sub="page" />
          ))}
          {files.map((f) => (
            <FallbackRow
              key={f.id}
              href={`/f/${f.id}?skill=${skill}`}
              name={f.name}
              sub={f.content_type || "file"}
            />
          ))}
          {tables.map((t) => (
            <FallbackRow
              key={t.id}
              href={`/tables/${t.id}?skill=${skill}`}
              name={t.name}
              sub="table"
            />
          ))}
          {pages.length === 0 && files.length === 0 && tables.length === 0 && (
            <p className="text-[13px] text-muted-foreground">Folder is empty.</p>
          )}
        </div>
      </div>
    </div>
  );
}

function FallbackRow({ href, name, sub }: { href: string; name: string; sub: string }) {
  return (
    <Link
      href={href}
      className="flex items-center gap-2.5 rounded-md px-2 py-1.5 hover:bg-raised"
    >
      <span className="min-w-0 flex-1">
        <span className="block truncate text-[13.5px] font-medium text-foreground">{name}</span>
        <span className="block truncate text-[11.5px] text-muted-foreground">{sub}</span>
      </span>
      <span className="hidden text-[11.5px] text-muted-foreground sm:inline">Open →</span>
    </Link>
  );
}
