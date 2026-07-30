"use client";

import { useCallback, useEffect, useState } from "react";
import { Sparkles } from "lucide-react";

import { installSkill, listAppSkills, listSkills, type Skill } from "@/lib/api";
import type { CuratedSkill, LaunchableSkill } from "@/lib/types";
import SkillLauncher from "@/components/skill/SkillLauncher";

// What your agent can do with everything in this app. A saved library is inert
// until something reads it, and nothing in the app itself says an agent can —
// so the skills built for this table are listed here.
//
// A skill you haven't added shows Add, not Run. Adding is the user's decision:
// an agent only ever runs what is in your Skills, and running one would have
// meant putting it there on your behalf.
//
// Renders nothing when no such skill is published: an empty strip would be
// worse than no strip, and this is the honest signal that the library skills
// aren't in Discover yet.
export default function AppSkillsBanner({ slug }: { slug: string }) {
  const [curated, setCurated] = useState<CuratedSkill[]>([]);
  // Held skills by frontmatter name, so a Run opens the launcher on the real
  // skill — its own description and when_to_use, not the catalog blurb.
  const [held, setHeld] = useState<Map<string, Skill>>(new Map());
  const [adding, setAdding] = useState<string | null>(null);
  const [launching, setLaunching] = useState<LaunchableSkill | null>(null);
  const [error, setError] = useState("");

  const loadHeld = useCallback(async () => {
    const mine = await listSkills();
    setHeld(new Map(mine.map((s) => [s.name, s])));
  }, []);

  useEffect(() => {
    let cancelled = false;
    Promise.all([listAppSkills(slug), listSkills()])
      .then(([forApp, mine]) => {
        if (cancelled) return;
        setCurated(forApp);
        setHeld(new Map(mine.map((s) => [s.name, s])));
      })
      .catch(() => {
        if (!cancelled) setCurated([]);
      });
    return () => {
      cancelled = true;
    };
  }, [slug]);

  async function add(skill: CuratedSkill) {
    setAdding(skill.name);
    setError("");
    try {
      await installSkill(skill.slug);
      await loadHeld();
    } catch (e) {
      setError(e instanceof Error ? e.message : `Couldn't add ${skill.name}`);
    } finally {
      setAdding(null);
    }
  }

  if (curated.length === 0) return null;

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
          {curated.map((skill) => {
            const mine = held.get(skill.name);
            return (
              <button
                key={skill.name}
                type="button"
                title={skill.description}
                disabled={adding === skill.name}
                onClick={() =>
                  mine
                    ? setLaunching({
                        name: mine.name,
                        description: mine.description,
                        when_to_use: mine.when_to_use,
                      })
                    : void add(skill)
                }
                className={
                  "cursor-pointer rounded-full border px-2.5 py-0.5 text-[12px] transition-colors disabled:opacity-50 " +
                  (mine
                    ? "border-border bg-base text-foreground hover:border-[var(--color-brand-300)] hover:bg-[var(--color-brand-50)] hover:text-[var(--color-brand-700)]"
                    : "border-dashed border-border bg-transparent text-muted-foreground hover:border-[var(--color-brand-300)] hover:text-foreground")
                }
              >
                {mine ? skill.name : `+ ${skill.name}`}
              </button>
            );
          })}
        </div>
        {error && <span className="text-[12px] text-red-500">{error}</span>}
      </div>
      {launching && (
        <SkillLauncher skill={launching} onClose={() => setLaunching(null)} />
      )}
    </>
  );
}
