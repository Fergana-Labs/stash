"use client";

import { useEffect, useState } from "react";
import { Sparkles } from "lucide-react";

import { listAppSkills } from "@/lib/api";
import type { LaunchableSkill } from "@/lib/types";
import SkillLauncher from "@/components/skill/SkillLauncher";

// What your agent can do with everything in this app. A saved library is
// inert until something reads it, and nothing in the app itself says that an
// agent can — so the skills that operate on this table are listed here, each
// one runnable in place.
//
// Renders nothing when no such skill is published: an empty strip would be
// worse than no strip, and this is the honest signal that the library skills
// aren't in Discover yet.
export default function AppSkillsBanner({ slug }: { slug: string }) {
  const [skills, setSkills] = useState<LaunchableSkill[]>([]);
  const [launching, setLaunching] = useState<LaunchableSkill | null>(null);

  useEffect(() => {
    let cancelled = false;
    listAppSkills(slug)
      .then((list) => {
        if (!cancelled) setSkills(list);
      })
      .catch(() => {
        if (!cancelled) setSkills([]);
      });
    return () => {
      cancelled = true;
    };
  }, [slug]);

  if (skills.length === 0) return null;

  return (
    <>
      {/* brand-50 is a light-theme tint; in dark it reads as a grey band, so
          the dark side gets the brand hue at low alpha instead. */}
      <div className="flex flex-wrap items-center gap-x-3 gap-y-2 border-b border-border bg-[var(--color-brand-50)]/50 px-6 py-2.5 dark:bg-[var(--color-brand-600)]/10">
        <span className="inline-flex items-center gap-1.5 text-[12px] font-medium text-foreground">
          <Sparkles className="h-3.5 w-3.5 text-[var(--color-brand-600)]" />
          Put these to work
        </span>
        <span className="text-[12px] text-muted-foreground">
          Hand your library to an agent:
        </span>
        <div className="flex flex-wrap items-center gap-1.5">
          {skills.map((skill) => (
            <button
              key={skill.name}
              type="button"
              title={skill.description}
              onClick={() => setLaunching(skill)}
              className="cursor-pointer rounded-full border border-border bg-base px-2.5 py-0.5 text-[12px] text-foreground transition-colors hover:border-[var(--color-brand-300)] hover:bg-[var(--color-brand-50)] hover:text-[var(--color-brand-700)]"
            >
              {skill.name}
            </button>
          ))}
        </div>
      </div>
      {launching && (
        <SkillLauncher skill={launching} onClose={() => setLaunching(null)} />
      )}
    </>
  );
}
