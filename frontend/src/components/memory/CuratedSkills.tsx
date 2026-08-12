"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { SkeletonBlock } from "@/components/SkeletonStates";
import { getCuratorSkills, type CuratorSkill } from "@/lib/api";

/** The curator's reserved slots. Three skills is few enough to read in a
 *  minute, which is the whole review mechanism: these load into every agent
 *  session, so the user has to be able to see what they say at a glance. */
export default function CuratedSkills() {
  const [skills, setSkills] = useState<CuratorSkill[] | null>(null);
  const [maxSlots, setMaxSlots] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const [loaded, setLoaded] = useState(false);

  useEffect(() => {
    let cancelled = false;
    getCuratorSkills()
      .then((data) => {
        if (cancelled) return;
        setSkills(data.skills);
        setMaxSlots(data.max_slots);
      })
      .catch((e) => {
        if (!cancelled) setError(e instanceof Error ? e.message : "Failed to load curated skills");
      })
      .finally(() => {
        if (!cancelled) setLoaded(true);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  if (!loaded) {
    return (
      <section>
        <div className="sys-label mb-1.5">Curated skills</div>
        <SkeletonBlock className="h-[120px] w-full" />
      </section>
    );
  }

  // "No skills yet" is a claim about the curator — never make it on a failure.
  if (error) {
    return (
      <section>
        <div className="sys-label mb-1.5">Curated skills</div>
        <div className="card-soft px-4 py-6 text-center text-[12.5px] text-destructive">
          Couldn&apos;t load your curated skills: {error}
        </div>
      </section>
    );
  }

  return (
    <section>
      <div className="mb-1.5 flex items-baseline justify-between gap-2">
        <div className="sys-label">Curated skills</div>
        {skills && skills.length > 0 && (
          <span className="text-[11.5px] text-dim">
            {skills.length}/{maxSlots} slots
          </span>
        )}
      </div>
      {!skills || skills.length === 0 ? (
        <div className="card-soft px-4 py-6 text-center text-[12.5px] text-muted-foreground">
          None yet. When the curator finds a procedure you repeat — and
          correct — it writes one here, and your agents load it everywhere.
        </div>
      ) : (
        <div className="flex flex-col gap-2.5">
          {skills.map((skill) => (
            <SkillCard key={skill.folder_id} skill={skill} />
          ))}
        </div>
      )}
    </section>
  );
}

function SkillCard({ skill }: { skill: CuratorSkill }) {
  return (
    <article className="card px-4 py-3.5">
      <div className="flex items-baseline justify-between gap-2">
        <span className="text-[13.5px] font-medium text-foreground">{skill.name}</span>
        <Link
          href={`/skills/folder/${skill.folder_id}`}
          className="shrink-0 text-[11.5px] text-dim hover:text-foreground"
        >
          Open →
        </Link>
      </div>
      {/* The description, not the body: it's the only text an agent matches
          on, so it's the only text that decides when this fires. */}
      <p className="mt-1.5 text-[13px] leading-[1.6] text-muted-foreground">
        {skill.description}
      </p>
    </article>
  );
}
