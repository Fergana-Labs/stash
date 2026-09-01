"use client";

import {
  ArrowLeft,
  File,
  FilePlus2,
  FileText,
  Folder,
  Pencil,
  Plus,
  Table2,
  Trash2,
  Upload,
} from "lucide-react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useEffect, useMemo, useRef, useState } from "react";
import { useBreadcrumbs } from "@/components/BreadcrumbContext";
import { useConfirm } from "@/components/ConfirmDialog";
import { useShareAction } from "@/components/ShellChromeContext";
import { FileBrowserSkeleton } from "@/components/SkeletonStates";
import ResourceShareButton from "@/components/share/ResourceShareButton";
import FileBrowser from "@/components/content/file-browser/FileBrowser";
import MarkdownEditor from "@/components/content/MarkdownEditor";
import SkillEnabledToggle from "@/components/skill/SkillEnabledToggle";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { useAuth } from "@/hooks/useAuth";
import {
  fileDownloadUrl,
  createPage,
  getFolderContents,
  getPage,
  listSkills,
  trashItem,
  updatePage,
  uploadFileOrPage,
  type FolderContents,
  type Skill,
} from "@/lib/api";
import { SKILL_MD, stripFrontmatter } from "@/lib/localSkill";
import { refreshSidebar } from "@/lib/skillNavigationCache";
import type { Page } from "@/lib/types";

// The Skill root presents instructions plus supporting files. Subfolders use
// the ordinary browser, but their links stay inside the Skill route.
export default function SkillFolderClient({ folderId }: { folderId: string }) {
  const router = useRouter();
  const confirm = useConfirm();
  const searchParams = useSearchParams();
  const selectedPageId = searchParams.get("page");
  const { user, loading } = useAuth();
  const userId = user?.id;

  const [contents, setContents] = useState<FolderContents | null>(null);
  const [skill, setSkill] = useState<Skill | null>(null);
  const [instructions, setInstructions] = useState<Page | null>(null);
  const [skillInstructionsId, setSkillInstructionsId] = useState<string | null>(null);
  const [savingInstructions, setSavingInstructions] = useState(false);
  const [error, setError] = useState("");
  const [renameTarget, setRenameTarget] = useState<{
    pageId: string;
    location: "sidebar" | "toolbar";
    value: string;
  } | null>(null);
  const uploadInputRef = useRef<HTMLInputElement | null>(null);

  useEffect(() => {
    if (!loading && !userId) router.push("/login");
  }, [userId, loading, router]);

  useEffect(() => {
    if (!userId) return;
    let cancelled = false;
    setContents(null);
    getFolderContents(folderId)
      .then(async (c) => {
        if (cancelled) return;
        // A non-skill folder doesn't belong on this route — bounce to Files.
        if (!c.folder.is_skill && !c.breadcrumbs.some((b) => b.is_skill)) {
          router.replace(`/folders/${folderId}`);
          return;
        }
        if (c.folder.is_skill) {
          const skillPage = c.pages.find((page) => page.name === SKILL_MD);
          if (!skillPage)
            throw new Error("This Skill is missing its SKILL.md instructions");
          const selectedPage = selectedPageId
            ? c.pages.find((page) => page.id === selectedPageId)
            : skillPage;
          if (!selectedPage)
            throw new Error("This file does not belong to this Skill");
          const [page, listed] = await Promise.all([
            getPage(selectedPage.id),
            listSkills(),
          ]);
          if (cancelled) return;
          const match = listed.find((entry) => entry.folder_id === folderId);
          if (!match) throw new Error("This Skill is not in your Skills list");
          setInstructions(page);
          setSkillInstructionsId(skillPage.id);
          setSkill(match);
        } else {
          setInstructions(null);
          setSkillInstructionsId(null);
          setSkill(null);
        }
        setContents(c);
      })
      .catch((e) => {
        if (!cancelled)
          setError(e instanceof Error ? e.message : "Failed to load skill");
      });
    return () => {
      cancelled = true;
    };
  }, [userId, folderId, router, selectedPageId]);

  const crumbs = useMemo(() => {
    if (!contents) return [{ label: "Skills", href: `/skills` }];
    const firstSkillIndex = contents.breadcrumbs.findIndex((b) => b.is_skill);
    const trail = contents.breadcrumbs
      .slice(firstSkillIndex === -1 ? 0 : firstSkillIndex, -1)
      .map((cr) => ({
        label: cr.name,
        href: `/skills/folder/${cr.id}`,
      }));
    return [
      { label: "Skills", href: `/skills` },
      ...trail,
      { label: contents.folder.name },
    ];
  }, [contents]);

  useBreadcrumbs(
    crumbs,
    `skills/${folderId}/${crumbs.map((c) => c.label).join("/")}`,
  );

  // Skill actions live on the skill root; subfolders are plain browsing.
  const isSkillRoot = !!contents?.folder.is_skill;
  const folderName = contents?.folder.name ?? "";
  // Skill sharing lives beside the Skill itself. Registering it in the shell
  // creates an otherwise-empty full-width action bar above the editor.
  useShareAction(null);

  if (loading) return <FileBrowserSkeleton />;
  if (!user) return null;
  if (error) {
    return (
      <div className="mx-auto max-w-md py-24 text-center">
        <h1 className="font-display text-[24px] font-bold text-foreground">
          Skill unavailable
        </h1>
        <p className="mt-2 text-[14px] leading-relaxed text-dim">{error}</p>
        <Link
          href="/skills"
          className="mt-5 inline-flex items-center gap-1.5 rounded-md border border-border bg-base px-3 py-2 text-[13px] font-medium text-foreground hover:bg-raised"
        >
          <ArrowLeft className="h-3.5 w-3.5" />
          Go back to Skills
        </Link>
      </div>
    );
  }
  if (!contents) return <FileBrowserSkeleton />;

  async function saveInstructions(content: string) {
    if (!instructions || !content.trim()) return;
    setSavingInstructions(true);
    setError("");
    try {
      const updated = await updatePage(instructions.id, {
        content,
      });
      setInstructions(updated);
      if (instructions.id === skillInstructionsId) await reloadSkill();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to save instructions");
    } finally {
      setSavingInstructions(false);
    }
  }

  async function reloadSkill() {
    const listed = await listSkills();
    const match = listed.find((entry) => entry.folder_id === folderId);
    if (!match) throw new Error("This Skill is not in your Skills list");
    setSkill(match);
  }

  async function uploadSupportingFiles(files: File[]) {
    setError("");
    try {
      for (const file of files) {
        await uploadFileOrPage(file, folderId);
      }
      setContents(await getFolderContents(folderId));
      await refreshSidebar();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to add files");
    }
  }

  async function createMarkdownFile() {
    setError("");
    try {
      const page = await createPage("Untitled.md", folderId);
      router.push(`/skills/folder/${folderId}?page=${page.id}`);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to create Markdown file");
    }
  }

  async function deleteSupportingPage(page: { id: string; name: string }) {
    const confirmed = await confirm({
      title: `Delete "${page.name}"?`,
      body: "This page will be moved to Trash.",
      confirmLabel: "Delete",
    });
    if (!confirmed) return;
    setError("");
    try {
      await trashItem("page", page.id);
      setContents(await getFolderContents(folderId));
      if (instructions?.id === page.id) {
        router.push(`/skills/folder/${folderId}`);
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to delete page");
    }
  }

  function startRenaming(page: { id: string; name: string }, location: "sidebar" | "toolbar") {
    if (page.id === skillInstructionsId) return;
    setRenameTarget({ pageId: page.id, location, value: page.name });
  }

  async function finishRenaming(page: { id: string; name: string }) {
    if (renameTarget?.pageId !== page.id) return;
    const name = renameTarget.value.trim();
    setRenameTarget(null);
    if (!name || name === page.name) return;
    setError("");
    try {
      const updated = await updatePage(page.id, { name });
      if (instructions?.id === page.id) setInstructions(updated);
      setContents(await getFolderContents(folderId));
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to rename page");
    }
  }

  if (isSkillRoot && instructions && skill && skillInstructionsId) {
    const showingSkillInstructions = instructions.id === skillInstructionsId;
    return (
      <div className="flex min-h-0 flex-1 overflow-hidden bg-background">
        <aside className="scroll-thin flex w-64 shrink-0 flex-col overflow-y-auto border-r border-border-subtle bg-surface/40">
          <div className="border-b border-border-subtle px-4 py-4">
            <Link
              href="/skills"
              className="inline-flex items-center gap-1.5 text-[12px] font-medium text-muted-foreground hover:text-foreground"
            >
              <ArrowLeft className="h-3.5 w-3.5" />
              All Skills
            </Link>
          </div>

          <div className="flex items-center justify-between px-3 pb-1 pt-3">
            <span className="sys-label">Files</span>
            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <button
                  type="button"
                  aria-label="Add to Skill"
                  className="cursor-pointer rounded p-1 text-muted-foreground hover:bg-raised hover:text-foreground"
                >
                  <Plus className="h-3.5 w-3.5" />
                </button>
              </DropdownMenuTrigger>
              <DropdownMenuContent align="end" className="w-48 text-[12.5px]">
                <DropdownMenuItem onSelect={() => void createMarkdownFile()}>
                  <FilePlus2 />
                  New Markdown file
                </DropdownMenuItem>
                <DropdownMenuItem onSelect={() => uploadInputRef.current?.click()}>
                  <Upload />
                  Upload file
                </DropdownMenuItem>
              </DropdownMenuContent>
            </DropdownMenu>
          </div>

          <nav aria-label="Skill files" className="px-2 pb-4">
            <SkillFileRow
              active={showingSkillInstructions}
              href={`/skills/folder/${folderId}`}
              icon={<FileText />}
              label="SKILL.md"
            />
            {contents.pages
              .filter((page) => page.id !== skillInstructionsId)
              .map((page) => (
                <SkillFileRow
                  key={page.id}
                  active={page.id === instructions.id}
                  href={`/skills/folder/${folderId}?page=${page.id}`}
                  icon={<FileText />}
                  label={page.name}
                  onDelete={() => void deleteSupportingPage(page)}
                  onRenameStart={() => startRenaming(page, "sidebar")}
                  rename={
                    renameTarget?.pageId === page.id &&
                    renameTarget.location === "sidebar"
                      ? {
                          value: renameTarget.value,
                          onChange: (value) =>
                            setRenameTarget((target) =>
                              target ? { ...target, value } : target,
                            ),
                          onCommit: () => void finishRenaming(page),
                          onCancel: () => setRenameTarget(null),
                        }
                      : undefined
                  }
                />
              ))}
            {contents.subfolders.map((folder) => (
              <SkillFileRow
                key={folder.id}
                href={`/skills/folder/${folder.id}`}
                icon={<Folder />}
                label={folder.name}
              />
            ))}
            {contents.files.map((file) => (
              <SkillFileRow
                key={file.id}
                href={fileDownloadUrl(file.id)}
                icon={<File />}
                label={file.name}
              />
            ))}
            {contents.tables.map((table) => (
              <SkillFileRow
                key={table.id}
                href={`/tables/${table.id}`}
                icon={<Table2 />}
                label={table.name}
              />
            ))}
          </nav>
        </aside>

        <main className="flex min-w-0 flex-1 flex-col overflow-hidden">
          {error && (
            <div className="border-b border-red-300/40 bg-red-500/10 px-4 py-2 text-[13px] text-red-500">
              {error}
            </div>
          )}
          <div className="scroll-thin min-h-0 flex-1 overflow-y-auto">
            <MarkdownEditor
              file={instructions}
              onSave={saveInstructions}
              alwaysEditing
              previewMarkdown={showingSkillInstructions ? stripFrontmatter : undefined}
              toolbarLeading={(
                renameTarget?.pageId === instructions.id &&
                renameTarget.location === "toolbar" ? (
                  <RenameInput
                    value={renameTarget.value}
                    label={`Rename ${instructions.name}`}
                    onChange={(value) =>
                      setRenameTarget((target) =>
                        target ? { ...target, value } : target,
                      )
                    }
                    onCommit={() => void finishRenaming(instructions)}
                    onCancel={() => setRenameTarget(null)}
                  />
                ) : showingSkillInstructions ? (
                  <span className="block max-w-full truncate font-mono text-[12.5px] text-muted-foreground">
                    {instructions.name}
                  </span>
                ) : (
                  <button
                    type="button"
                    aria-label={`Rename ${instructions.name}`}
                    onClick={() => startRenaming(instructions, "toolbar")}
                    className="block max-w-full cursor-text truncate font-mono text-[12.5px] text-muted-foreground hover:text-foreground"
                  >
                    {instructions.name}
                  </button>
                )
              )}
              toolbarCenter={(
                <span className="block max-w-[40vw] truncate text-[12.5px] font-medium text-foreground">
                  {skill.name}
                </span>
              )}
              toolbarActions={(
                <>
                  {savingInstructions && (
                    <span className="text-[11px] text-muted-foreground">Saving…</span>
                  )}
                  <SkillEnabledToggle skill={skill} onChanged={reloadSkill} />
                  <ResourceShareButton
                    objectType="folder"
                    objectId={folderId}
                    resourceName={folderName}
                    resourceUrlPath={`/skills/folder/${folderId}`}
                    currentUser={user}
                  />
                </>
              )}
            />
          </div>
        </main>

        <input
          ref={uploadInputRef}
          type="file"
          multiple
          className="hidden"
          onChange={(event) => {
            const files = Array.from(event.target.files ?? []);
            event.target.value = "";
            if (files.length > 0) void uploadSupportingFiles(files);
          }}
        />
      </div>
    );
  }

  return (
    <FileBrowser
      folderId={folderId}
      folderHrefBase={`/skills/folder`}
      breadcrumbs={crumbs}
    />
  );
}

function SkillFileRow({
  active = false,
  href,
  icon,
  label,
  onDelete,
  onRenameStart,
  rename,
}: {
  active?: boolean;
  href?: string;
  icon: React.ReactElement;
  label: string;
  onDelete?: () => void;
  onRenameStart?: () => void;
  rename?: {
    value: string;
    onChange: (value: string) => void;
    onCommit: () => void;
    onCancel: () => void;
  };
}) {
  if (rename) {
    return (
      <div className="flex items-center gap-2 rounded-md bg-raised px-2 py-1 text-[12.5px] text-foreground">
        <span className="[&>svg]:h-3.5 [&>svg]:w-3.5">{icon}</span>
        <RenameInput
          value={rename.value}
          label={`Rename ${label}`}
          onChange={rename.onChange}
          onCommit={rename.onCommit}
          onCancel={rename.onCancel}
        />
      </div>
    );
  }

  const content = (
    <>
      <span className="[&>svg]:h-3.5 [&>svg]:w-3.5">{icon}</span>
      <span className="min-w-0 truncate">{label}</span>
    </>
  );
  const stateClass =
    active
      ? "bg-raised font-medium text-foreground"
      : "text-muted-foreground hover:bg-raised hover:text-foreground";
  const className = `flex items-center gap-2 rounded-md px-2 py-1.5 text-[12.5px] ${stateClass}`;

  if (!href) {
    return <div className={className}>{content}</div>;
  }
  if (onDelete) {
    return (
      <div className={`group flex items-center rounded-md pr-1 text-[12.5px] ${stateClass}`}>
        <Link
          href={href}
          className="flex min-w-0 flex-1 items-center gap-2 px-2 py-1.5"
        >
          {content}
        </Link>
        {onRenameStart && (
          <button
            type="button"
            aria-label={`Rename ${label}`}
            onClick={onRenameStart}
            className="cursor-pointer rounded p-1 text-muted-foreground opacity-0 hover:bg-background hover:text-foreground focus:opacity-100 group-hover:opacity-100"
          >
            <Pencil className="h-3.5 w-3.5" />
          </button>
        )}
        <button
          type="button"
          aria-label={`Delete ${label}`}
          onClick={onDelete}
          className="cursor-pointer rounded p-1 text-muted-foreground opacity-0 hover:bg-background hover:text-red-500 focus:opacity-100 group-hover:opacity-100"
        >
          <Trash2 className="h-3.5 w-3.5" />
        </button>
      </div>
    );
  }
  return (
    <Link href={href} className={className}>
      {content}
    </Link>
  );
}

function RenameInput({
  value,
  label,
  onChange,
  onCommit,
  onCancel,
}: {
  value: string;
  label: string;
  onChange: (value: string) => void;
  onCommit: () => void;
  onCancel: () => void;
}) {
  return (
    <input
      autoFocus
      aria-label={label}
      value={value}
      onChange={(event) => onChange(event.target.value)}
      onFocus={(event) => event.currentTarget.select()}
      onBlur={onCommit}
      onKeyDown={(event) => {
        if (event.key === "Enter") event.currentTarget.blur();
        if (event.key === "Escape") onCancel();
      }}
      className="min-w-0 flex-1 rounded border border-brand-500 bg-background px-1.5 py-0.5 font-mono text-[12.5px] text-foreground outline-none"
    />
  );
}
