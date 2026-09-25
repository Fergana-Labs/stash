"use client";

import { ChevronDown, ChevronRight } from "lucide-react";
import Link from "next/link";
import { useCallback, useEffect, useRef, useState } from "react";
import { listSkills, setSkillAgentEnabled, type Skill } from "@/lib/api";

/** The Skills currently switched on for the user's agents. Off Skills stay
 *  out of view — the "Enable more" menu is the only place they show up on
 *  Home, so the page reads as what is running right now. */
export default function ActiveSkills() {
  const [skills, setSkills] = useState<Skill[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      setSkills(await listSkills());
      setError(null);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Could not load Skills");
    }
  }, []);

  useEffect(() => void load(), [load]);

  const active = skills?.filter((skill) => skill.agent_enabled) ?? null;
  const inactive = skills?.filter((skill) => !skill.agent_enabled) ?? [];

  return (
    <section className="rounded-2xl border border-border bg-surface p-6">
      <div className="flex items-start justify-between gap-4">
        <div>
          <h2 className="font-display text-[16px] font-semibold text-foreground">
            Active Skills
          </h2>
          <p className="mt-0.5 text-[12.5px] text-muted-foreground">
            What your coding agents are using right now.
          </p>
        </div>
        <div className="flex shrink-0 items-center gap-2">
          {inactive.length > 0 && (
            <EnableMoreMenu skills={inactive} onEnabled={load} />
          )}
          <Link
            href="/skills"
            className="rounded-md px-2 py-1.5 text-[12.5px] text-muted-foreground hover:bg-raised hover:text-foreground"
          >
            Manage all
          </Link>
        </div>
      </div>

      <div className="mt-5">
        {error ? (
          <p className="text-[12.5px] text-destructive">Couldn&apos;t load: {error}</p>
        ) : active === null ? (
          <div className="h-[58px] animate-pulse rounded-xl bg-raised" />
        ) : active.length === 0 ? (
          <div className="rounded-xl border border-border bg-base px-4 py-3 text-[12.5px] text-muted-foreground">
            {inactive.length === 0
              ? "No Skills yet. Stash will create them as it learns from your agent traces."
              : "No Skills are on. Enable one to hand it to your agents."}
          </div>
        ) : (
          <div className="divide-y divide-border border-y border-border">
            {active.map((skill) => (
              <Link
                key={skillKey(skill)}
                href={skillHref(skill)}
                className="group -mx-3 flex items-center gap-3 rounded-md px-3 py-3 transition-colors hover:bg-raised"
              >
                <span className="min-w-0 flex-1">
                  <span className="block truncate text-[13px] font-medium text-foreground group-hover:text-brand-600">
                    {skill.name}
                  </span>
                  <span className="block truncate text-[11.5px] text-muted-foreground">
                    {skill.description || "No description"}
                  </span>
                </span>
                <ChevronRight className="h-4 w-4 shrink-0 text-muted-foreground group-hover:text-brand-600" />
              </Link>
            ))}
          </div>
        )}
      </div>
    </section>
  );
}

function EnableMoreMenu({
  skills,
  onEnabled,
}: {
  skills: Skill[];
  onEnabled: () => Promise<void>;
}) {
  const [open, setOpen] = useState(false);
  const [saving, setSaving] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const menuRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    if (!open) return;
    function closeOnOutsideClick(event: MouseEvent) {
      if (!menuRef.current?.contains(event.target as Node)) setOpen(false);
    }
    document.addEventListener("mousedown", closeOnOutsideClick);
    return () => document.removeEventListener("mousedown", closeOnOutsideClick);
  }, [open]);

  async function enable(skill: Skill) {
    setSaving(skillKey(skill));
    setError(null);
    try {
      await setSkillAgentEnabled(skill, true);
      await onEnabled();
      setOpen(false);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Could not enable Skill");
    } finally {
      setSaving(null);
    }
  }

  return (
    <div ref={menuRef} className="relative">
      <button
        type="button"
        aria-haspopup="menu"
        aria-expanded={open}
        onClick={() => setOpen((value) => !value)}
        className="flex cursor-pointer items-center gap-1 rounded-md border border-border bg-base px-3 py-1.5 text-[12.5px] font-medium text-foreground hover:bg-raised"
      >
        Enable more
        <ChevronDown className="h-3.5 w-3.5" />
      </button>
      {open && (
        <div
          role="menu"
          className="absolute right-0 z-20 mt-1 w-72 overflow-hidden rounded-lg border border-border bg-surface py-1 shadow-lg"
        >
          {skills.map((skill) => {
            const key = skillKey(skill);
            return (
              <button
                key={key}
                type="button"
                role="menuitem"
                disabled={saving !== null}
                onClick={() => void enable(skill)}
                className="block w-full cursor-pointer px-3 py-2 text-left hover:bg-raised disabled:opacity-50"
              >
                <span className="block truncate text-[13px] font-medium text-foreground">
                  {saving === key ? "Enabling…" : skill.name}
                </span>
                <span className="block truncate text-[11.5px] text-muted-foreground">
                  {skill.description || "No description"}
                </span>
              </button>
            );
          })}
          {error && <div className="px-3 py-2 text-[11.5px] text-error">{error}</div>}
        </div>
      )}
    </div>
  );
}

function skillHref(skill: Skill): string {
  return skill.backing === "folder"
    ? `/skills/folder/${skill.folder_id}`
    : `/skills/source/${encodeURIComponent(skill.source_ref)}`;
}

function skillKey(skill: Skill): string {
  return skill.backing === "folder" ? skill.folder_id : skill.source_ref;
}
