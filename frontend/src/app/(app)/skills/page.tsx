"use client";

import { ChevronRight } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";
import { SkillComposer } from "@/components/skill/SkillComposer";
import SkillEnabledToggle from "@/components/skill/SkillEnabledToggle";
import { useAuth } from "@/hooks/useAuth";
import {
  createSkill,
  installSuggestedSkill,
  listSkills,
  listSuggestedSkills,
  requestSkill,
  type Skill,
  type SuggestedSkill,
} from "@/lib/api";
import { refreshSidebar } from "@/lib/skillNavigationCache";

export default function SkillsPage() {
  const router = useRouter();
  const { user } = useAuth();
  const [skills, setSkills] = useState<Skill[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [suggestions, setSuggestions] = useState<SuggestedSkill[] | null>(null);
  const [advancedOpen, setAdvancedOpen] = useState(false);
  const [composerOpen, setComposerOpen] = useState(false);
  const composerRef = useRef<HTMLDivElement | null>(null);

  const load = useCallback(async () => {
    try {
      const [nextSkills, nextSuggestions] = await Promise.all([
        listSkills(),
        listSuggestedSkills(),
      ]);
      setSkills(nextSkills);
      setSuggestions(nextSuggestions);
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

        <SuggestedSkills
          suggestions={suggestions}
          onInstalled={async (created) => {
            if (user) await refreshSidebar();
            router.push(`/skills/folder/${created.folder_id}`);
          }}
        />

        <RequestSkill
          onCreated={async (created) => {
            if (user) await refreshSidebar();
            router.push(`/skills/folder/${created.folder_id}`);
          }}
        />

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

/** The bootstrap catalog: "did you know people have made a Skill for this?"
 *  Each card adds a complete, working Skill in one click. Already-added
 *  entries drop out so the section only ever offers something new. */
function SuggestedSkills({
  suggestions,
  onInstalled,
}: {
  suggestions: SuggestedSkill[] | null;
  onInstalled: (created: { folder_id: string; name: string }) => Promise<void>;
}) {
  const [installingKey, setInstallingKey] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const available = suggestions?.filter((s) => !s.installed) ?? [];
  if (suggestions === null || available.length === 0) return null;

  async function install(key: string) {
    setInstallingKey(key);
    setError(null);
    try {
      await onInstalled(await installSuggestedSkill(key));
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Could not add Skill");
      setInstallingKey(null);
    }
  }

  return (
    <section className="mt-10 border-t border-border pt-5">
      <h2 className="text-[15px] font-semibold text-foreground">
        What could you be automating?
      </h2>
      <p className="mt-1 text-[13px] text-muted-foreground">
        Ready-made Skills other people use every day. Add one and it works in
        your next session.
      </p>
      {error && <p className="mt-3 text-[12.5px] text-error">{error}</p>}
      <div className="mt-4 grid grid-cols-1 gap-3 sm:grid-cols-2">
        {available.map((suggestion) => (
          <div
            key={suggestion.key}
            className="flex flex-col rounded-lg border border-border bg-base p-4"
          >
            <div className="text-[13.5px] font-medium text-foreground">
              {suggestion.name}
            </div>
            <p className="mt-1 flex-1 text-[12.5px] leading-relaxed text-muted-foreground">
              {suggestion.description}
            </p>
            <div className="mt-3">
              <button
                type="button"
                disabled={installingKey !== null}
                onClick={() => void install(suggestion.key)}
                className="cursor-pointer rounded-md border border-border bg-surface px-3 py-1.5 text-[12.5px] font-medium text-foreground hover:bg-raised disabled:opacity-50"
              >
                {installingKey === suggestion.key ? "Adding…" : "Add Skill"}
              </button>
            </div>
          </div>
        ))}
      </div>
    </section>
  );
}

/** Ask for a Skill in plain language. Stash drafts it and opens it for the
 *  user to react to — a concrete draft beats an empty form. */
function RequestSkill({
  onCreated,
}: {
  onCreated: (created: { folder_id: string; name: string }) => Promise<void>;
}) {
  const [request, setRequest] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit() {
    if (!request.trim()) return;
    setSubmitting(true);
    setError(null);
    try {
      await onCreated(await requestSkill(request.trim()));
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Could not create Skill");
      setSubmitting(false);
    }
  }

  return (
    <section className="mt-10 border-t border-border pt-5">
      <h2 className="text-[15px] font-semibold text-foreground">Request a Skill</h2>
      <p className="mt-1 text-[13px] text-muted-foreground">
        Describe something you keep doing by hand. Stash drafts a Skill for it
        and opens the draft for you to edit.
      </p>
      <textarea
        aria-label="Describe the Skill you want"
        value={request}
        onChange={(event) => setRequest(event.target.value)}
        placeholder="e.g. Every Friday I write a release summary from the PRs merged that week, formatted for our #product channel."
        rows={3}
        className="mt-3 w-full resize-y rounded-lg border border-border bg-base px-3 py-2.5 text-[13px] leading-relaxed text-foreground outline-none placeholder:text-muted-foreground/70 focus:border-foreground/30"
      />
      {error && <p className="mt-2 text-[12.5px] text-error">{error}</p>}
      <div className="mt-2 flex items-center gap-3">
        <button
          type="button"
          disabled={submitting || !request.trim()}
          onClick={() => void submit()}
          className="cursor-pointer rounded-md bg-[var(--color-brand-600)] px-3 py-1.5 text-[12.5px] font-medium text-white hover:bg-[var(--color-brand-700)] disabled:cursor-default disabled:opacity-50"
        >
          {submitting ? "Drafting…" : "Draft this Skill"}
        </button>
        {submitting && (
          <span className="text-[12px] text-muted-foreground">
            Usually takes a few seconds.
          </span>
        )}
      </div>
    </section>
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
    <div className="group/row -mx-3 flex items-center gap-6 rounded-md px-3 py-4 transition-colors hover:bg-raised">
      <Link
        href={href}
        className="flex min-w-0 flex-1 items-center gap-3"
      >
        <span className="min-w-0 flex-1">
          <span className="block text-[14px] font-medium text-foreground group-hover/row:text-brand-600">
            {skill.name}
          </span>
          <span className="mt-0.5 block truncate text-[12.5px] text-muted-foreground">
            {skill.description || "No description"}
          </span>
        </span>
        <span className="flex shrink-0 items-center gap-1 text-[12px] text-muted-foreground group-hover/row:text-brand-600">
          <span className="opacity-0 transition-opacity group-hover/row:opacity-100">
            Open
          </span>
          <ChevronRight className="h-4 w-4" />
        </span>
      </Link>
      <SkillEnabledToggle skill={skill} onChanged={onChanged} />
    </div>
  );
}

function skillKey(skill: Skill): string {
  return skill.backing === "folder" ? skill.folder_id : skill.source_ref;
}
