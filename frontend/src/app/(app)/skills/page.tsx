"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";
import { SkillComposer } from "@/components/skill/SkillComposer";
import { useAuth } from "@/hooks/useAuth";
import {
  createSkill,
  listSkills,
  setSkillAgentEnabled,
  type Skill,
} from "@/lib/api";
import { refreshSidebar } from "@/lib/skillNavigationCache";
import { cn } from "@/lib/utils";

export default function SkillsPage() {
  const router = useRouter();
  const { user } = useAuth();
  const [skills, setSkills] = useState<Skill[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [advancedOpen, setAdvancedOpen] = useState(false);
  const [composerOpen, setComposerOpen] = useState(false);
  const composerRef = useRef<HTMLDivElement | null>(null);

  const load = useCallback(async () => {
    try {
      setSkills(await listSkills());
      setError(null);
    } catch (reason) {
      setError(
        reason instanceof Error ? reason.message : "Failed to load Skills",
      );
    }
  }, []);

  useEffect(() => void load(), [load]);

  function showComposer() {
    setComposerOpen(true);
    requestAnimationFrame(() => {
      composerRef.current
        ?.querySelector<HTMLElement>("input, textarea")
        ?.focus();
    });
  }

  async function newSkill({
    name,
    description,
  }: {
    name: string;
    description: string;
  }) {
    const created = await createSkill(name, description);
    if (user) await refreshSidebar();
    router.push(`/skills/folder/${created.folder_id}`);
  }

  return (
    <div className="scroll-thin flex-1 overflow-y-auto">
      <div className="mx-auto max-w-[920px] px-12 pb-20 pt-8">
        <div>
          <h1 className="font-display text-[21px] font-bold tracking-tight text-foreground">
            Skills
          </h1>
          <p className="mt-1 text-[13px] text-muted-foreground">
            Stash creates Skills from your traces. Choose which ones are
            available to your coding agents.
          </p>
        </div>
        {error && (
          <p className="mt-5 text-[13px] text-error">
            Couldn&apos;t load Skills: {error}
          </p>
        )}
        {skills === null ? (
          <div className="mt-8 h-28 animate-pulse rounded-md bg-raised" />
        ) : skills.length === 0 ? (
          <div className="mt-8 border-y border-border py-8 text-[13px] text-muted-foreground">
            No Skills yet. Stash will create them as it learns from your agent
            traces.
          </div>
        ) : (
          <div className="mt-8 divide-y divide-border border-y border-border">
            {skills.map((skill) => (
              <SkillRow key={skillKey(skill)} skill={skill} onChanged={load} />
            ))}
          </div>
        )}

        <div className="mt-10 border-t border-border pt-5">
          <button
            type="button"
            aria-expanded={advancedOpen}
            onClick={() => setAdvancedOpen((open) => !open)}
            className="cursor-pointer text-[13px] font-medium text-muted-foreground hover:text-foreground"
          >
            Advanced
          </button>
          {advancedOpen && (
            <div className="mt-4">
              <p className="text-[13px] text-muted-foreground">
                Create a Skill manually instead of waiting for Stash to derive
                one from your traces.
              </p>
              {!composerOpen && (
                <button
                  type="button"
                  onClick={showComposer}
                  className="mt-3 cursor-pointer rounded-md border border-border bg-base px-3 py-2 text-[13px] font-medium text-foreground hover:bg-raised"
                >
                  New Skill
                </button>
              )}
              {composerOpen && (
                <div ref={composerRef} className="mt-4">
                  <SkillComposer
                    onSubmit={newSkill}
                    onCancel={() => setComposerOpen(false)}
                  />
                </div>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

function SkillRow({
  skill,
  onChanged,
}: {
  skill: Skill;
  onChanged: () => Promise<void>;
}) {
  const href =
    skill.backing === "folder"
      ? `/skills/folder/${skill.folder_id}`
      : `/skills/source/${encodeURIComponent(skill.source_ref)}`;
  return (
    <div className="flex items-center gap-6 py-4">
      <Link href={href} className="min-w-0 flex-1">
        <div className="text-[14px] font-medium text-foreground">
          {skill.name}
        </div>
        <div className="mt-0.5 truncate text-[12.5px] text-muted-foreground">
          {skill.description || "No description"}
        </div>
      </Link>
      <SkillToggle skill={skill} onChanged={onChanged} />
    </div>
  );
}

function SkillToggle({
  skill,
  onChanged,
}: {
  skill: Skill;
  onChanged: () => Promise<void>;
}) {
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function toggle() {
    setSaving(true);
    setError(null);
    try {
      await setSkillAgentEnabled(skill, !skill.agent_enabled);
      await onChanged();
    } catch (reason) {
      setError(
        reason instanceof Error ? reason.message : "Could not update Skill",
      );
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="shrink-0">
      <button
        role="switch"
        aria-checked={skill.agent_enabled}
        disabled={saving}
        onClick={() => void toggle()}
        className="group flex cursor-pointer items-center gap-2 disabled:opacity-50"
      >
        <span
          className={cn(
            "relative h-5 w-9 rounded-full transition-colors",
            skill.agent_enabled
              ? "bg-brand-500"
              : "bg-border group-hover:bg-muted-foreground/40",
          )}
        >
          <span
            className={cn(
              "absolute top-0.5 h-4 w-4 rounded-full bg-white shadow-sm transition-[left]",
              skill.agent_enabled ? "left-[18px]" : "left-0.5",
            )}
          />
        </span>
        <span
          className={cn(
            "w-[82px] whitespace-nowrap text-left text-[13px]",
            skill.agent_enabled
              ? "font-medium text-brand-500"
              : "text-muted-foreground",
          )}
        >
          {skill.agent_enabled ? "Enabled" : "Not enabled"}
        </span>
      </button>
      {error && <div className="mt-1 text-[11px] text-error">{error}</div>}
    </div>
  );
}

function skillKey(skill: Skill): string {
  return skill.backing === "folder" ? skill.folder_id : skill.source_ref;
}
