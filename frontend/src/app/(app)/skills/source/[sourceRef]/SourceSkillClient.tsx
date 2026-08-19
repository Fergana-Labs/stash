"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import Markdown from "react-markdown";
import remarkGfm from "remark-gfm";

import { useBreadcrumbs } from "@/components/BreadcrumbContext";
import { FileBrowserSkeleton } from "@/components/SkeletonStates";
import ResyncSourceButton from "@/components/skill/ResyncSourceButton";
import { readSourceSkill, type SourceSkillRead } from "@/lib/api";

export default function SourceSkillClient({ sourceRef }: { sourceRef: string }) {
  const [skill, setSkill] = useState<SourceSkillRead | null>(null);
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    try {
      setSkill(await readSourceSkill(sourceRef));
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load this skill");
    }
  }, [sourceRef]);

  useEffect(() => {
    void load();
  }, [load]);

  useBreadcrumbs(
    [{ label: "Skills" }, { label: skill?.name ?? "Skill" }],
    `source-skill/${sourceRef}`
  );

  if (error) {
    return (
      <div className="mx-auto max-w-[820px] px-12 pt-8">
        <div className="rounded-lg border border-red-300/40 bg-red-500/10 px-4 py-2 text-[13px] text-red-500">
          {error}
        </div>
      </div>
    );
  }

  if (!skill) return <FileBrowserSkeleton />;

  return (
    <div className="scroll-thin flex-1 overflow-y-auto">
      <div className="mx-auto max-w-[820px] px-12 pb-20 pt-8">
        <Link href="/skills" className="text-[12.5px] text-muted-foreground hover:text-foreground">
          ← Skills
        </Link>

        <h1 className="m-0 mt-3 font-display text-[21px] font-bold tracking-tight text-foreground">
          {skill.name}
        </h1>
        {skill.description && (
          <p className="mt-1.5 text-[13px] leading-[1.55] text-dim">{skill.description}</p>
        )}

        <div className="mt-3 flex items-center gap-2 text-[11.5px] text-muted-foreground">
          <span className="rounded border border-border px-1.5 py-px font-medium">Drive</span>
          <span>
            Read from <span className="text-foreground">{skill.source_name}</span>. You can make
            edits in Google Drive and they&apos;ll sync back here automatically.
          </span>
          <ResyncSourceButton sourceId={skill.source_id} onRefresh={load} />
        </div>

        {skill.has_instructions ? (
          <article className="prose prose-sm markdown-content mt-6 text-foreground">
            <Markdown remarkPlugins={[remarkGfm]}>{skill.body}</Markdown>
          </article>
        ) : (
          // A document only reaches this page by declaring itself a skill, so
          // the empty case is always the same one: a frontmatter block with
          // nothing written under it.
          <div className="mt-6 rounded-lg border border-border bg-surface px-4 py-3 text-[13px] text-muted-foreground">
            This document declares itself a skill but has nothing below its frontmatter, so there
            are no instructions for an agent to follow.{" "}
            <a
              href={`https://drive.google.com/open?id=${skill.source_ref}`}
              target="_blank"
              rel="noreferrer"
              className="font-medium text-[var(--color-brand-700)] underline"
            >
              Add them in Google Drive
            </a>
            .
          </div>
        )}
      </div>
    </div>
  );
}
