"use client";

import { useRouter } from "next/navigation";
import Markdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { useEffect, useMemo, useState } from "react";
import { useBreadcrumbs } from "@/components/BreadcrumbContext";
import { useShareAction } from "@/components/ShellChromeContext";
import { FileBrowserSkeleton } from "@/components/SkeletonStates";
import ResourceShareButton from "@/components/share/ResourceShareButton";
import FileBrowser from "@/components/content/file-browser/FileBrowser";
import SkillEnabledToggle from "@/components/skill/SkillEnabledToggle";
import { useAuth } from "@/hooks/useAuth";
import {
  getFolderContents,
  getPage,
  listSkills,
  updatePage,
  type FolderContents,
  type Skill,
} from "@/lib/api";
import { SKILL_MD, stripFrontmatter } from "@/lib/localSkill";
import type { Page } from "@/lib/types";

// The Skill root presents instructions plus supporting files. Subfolders use
// the ordinary browser, but their links stay inside the Skill route.
export default function SkillFolderClient({ folderId }: { folderId: string }) {
  const router = useRouter();
  const { user, loading } = useAuth();
  const userId = user?.id;

  const [contents, setContents] = useState<FolderContents | null>(null);
  const [skill, setSkill] = useState<Skill | null>(null);
  const [instructions, setInstructions] = useState<Page | null>(null);
  const [editingInstructions, setEditingInstructions] = useState(false);
  const [instructionDraft, setInstructionDraft] = useState("");
  const [savingInstructions, setSavingInstructions] = useState(false);
  const [error, setError] = useState("");

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
          const [page, listed] = await Promise.all([
            getPage(skillPage.id),
            listSkills(),
          ]);
          if (cancelled) return;
          const match = listed.find((entry) => entry.folder_id === folderId);
          if (!match) throw new Error("This Skill is not in your Skills list");
          setInstructions(page);
          setSkill(match);
        } else {
          setInstructions(null);
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
  }, [userId, folderId, router]);

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
  const shareAction = useMemo(() => {
    if (!user || !isSkillRoot) return null;
    return (
      <ResourceShareButton
        objectType="folder"
        objectId={folderId}
        resourceName={folderName}
        resourceUrlPath={`/skills/folder/${folderId}`}
        currentUser={user}
      />
    );
  }, [user, isSkillRoot, folderId, folderName]);
  useShareAction(shareAction);

  if (loading) return <FileBrowserSkeleton />;
  if (!user) return null;
  if (error) {
    return (
      <div className="mx-auto max-w-md py-24 text-center">
        <h1 className="font-display text-[24px] font-bold text-foreground">
          Skill unavailable
        </h1>
        <p className="mt-2 text-[14px] leading-relaxed text-dim">{error}</p>
      </div>
    );
  }
  if (!contents) return <FileBrowserSkeleton />;

  const instructionBody = instructions
    ? withoutRepeatedTitle(
        stripFrontmatter(instructions.content_markdown),
        contents.folder.name,
      )
    : "";

  function beginEditingInstructions() {
    setInstructionDraft(instructionBody);
    setEditingInstructions(true);
  }

  async function saveInstructions() {
    if (!instructions || !instructionDraft.trim()) return;
    setSavingInstructions(true);
    setError("");
    try {
      const updated = await updatePage(instructions.id, {
        content: replaceSkillInstructions(
          instructions.content_markdown,
          instructionDraft,
        ),
      });
      setInstructions(updated);
      setEditingInstructions(false);
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

  // The Skill root reads like a repository page: a header with the
  // description, the enabled switch and the vitals, then the SKILL.md
  // rendered like a README with its own title bar, then the supporting files.
  const skillIntro = instructions && skill ? (
    <section className="mt-6 border-b border-border-subtle pb-8">
      <header className="flex flex-wrap items-start justify-between gap-4">
        <div className="min-w-0 flex-1">
          <h1 className="font-display text-[24px] font-bold tracking-tight text-foreground">
            {skill.name}
          </h1>
          <p className="mt-1.5 max-w-2xl text-[14px] leading-relaxed text-dim">
            {skill.description || "No description"}
          </p>
          {skill.when_to_use && (
            <p className="mt-2 max-w-2xl text-[13px] leading-relaxed text-muted-foreground">
              <span className="font-medium text-foreground">When to use:</span>{" "}
              {skill.when_to_use}
            </p>
          )}
        </div>
        <SkillEnabledToggle skill={skill} onChanged={reloadSkill} />
      </header>
      <dl className="mt-4 flex flex-wrap gap-x-5 gap-y-1 text-[12px] text-muted-foreground">
        <SkillStat label="Files" value={String(skill.file_count)} />
        <SkillStat label="Updated" value={formatSkillDate(skill.updated_at)} />
        {skill.version && <SkillStat label="Version" value={skill.version} />}
        <SkillStat
          label="Visibility"
          value={skill.published ? "Published" : "Private to you"}
        />
      </dl>

      <div className="mt-6 overflow-hidden rounded-lg border border-border">
        <div className="flex items-center justify-between border-b border-border bg-raised px-4 py-2">
          <span className="font-mono text-[12px] font-medium text-foreground">
            SKILL.md
          </span>
          {!editingInstructions && (
            <button
              type="button"
              onClick={beginEditingInstructions}
              className="cursor-pointer text-[12.5px] font-medium text-muted-foreground hover:text-foreground"
            >
              Edit instructions
            </button>
          )}
        </div>
        <div className="px-5 py-4">
      {editingInstructions ? (
        <div>
          <label
            htmlFor="skill-instructions"
            className="text-[13px] font-medium text-foreground"
          >
            Instructions
          </label>
          <textarea
            id="skill-instructions"
            value={instructionDraft}
            onChange={(event) => setInstructionDraft(event.target.value)}
            autoFocus
            className="mt-2 min-h-72 w-full resize-y rounded-lg border border-border bg-base px-3 py-2.5 font-mono text-[13px] leading-relaxed text-foreground outline-none focus:border-foreground/30"
          />
          <div className="mt-3 flex justify-end gap-2">
            <button
              type="button"
              onClick={() => setEditingInstructions(false)}
              disabled={savingInstructions}
              className="cursor-pointer rounded-md border border-border bg-base px-3 py-1.5 text-[12.5px] font-medium text-foreground hover:bg-raised disabled:opacity-50"
            >
              Cancel
            </button>
            <button
              type="button"
              onClick={() => void saveInstructions()}
              disabled={savingInstructions || !instructionDraft.trim()}
              className="cursor-pointer rounded-md bg-[var(--color-brand-600)] px-3 py-1.5 text-[12.5px] font-medium text-white hover:bg-[var(--color-brand-700)] disabled:cursor-default disabled:opacity-50"
            >
              {savingInstructions ? "Saving…" : "Save"}
            </button>
          </div>
        </div>
      ) : instructionBody ? (
        <div className="markdown-content">
          <Markdown remarkPlugins={[remarkGfm]}>{instructionBody}</Markdown>
        </div>
      ) : (
        <p className="text-[14px] text-muted-foreground">
          No instructions have been written yet.
        </p>
      )}
        </div>
      </div>
    </section>
  ) : null;

  return (
    <FileBrowser
      folderId={folderId}
      folderHrefBase={`/skills/folder`}
      breadcrumbs={crumbs}
      hiddenItemIds={instructions ? [instructions.id] : []}
      intro={skillIntro}
      itemsHeading={instructions ? "Supporting files" : undefined}
      supportingFilesMode={!!instructions}
    />
  );
}

function SkillStat({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-baseline gap-1">
      <dt className="text-muted-foreground/80">{label}</dt>
      <dd className="font-medium text-foreground">{value}</dd>
    </div>
  );
}

function formatSkillDate(iso: string): string {
  return new Date(iso).toLocaleDateString(undefined, {
    month: "short",
    day: "numeric",
    year: "numeric",
  });
}

function withoutRepeatedTitle(markdown: string, skillName: string): string {
  const lines = markdown.trim().split("\n");
  if (lines[0]?.trim() !== `# ${skillName}`) return markdown;
  return lines.slice(1).join("\n").trim();
}

function replaceSkillInstructions(markdown: string, instructions: string): string {
  const frontmatter = markdown.match(/^---\r?\n[\s\S]*?\r?\n---/);
  if (!frontmatter) {
    throw new Error("This Skill has invalid SKILL.md frontmatter");
  }
  return `${frontmatter[0]}\n\n${instructions.trim()}\n`;
}
