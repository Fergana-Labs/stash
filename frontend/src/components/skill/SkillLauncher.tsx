"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { Play, X } from "lucide-react";
import { useWorkspace } from "@/lib/workspace-store";
import { newRunTabRef, runPrompt, stageSkillRun } from "@/lib/skill-launch";
import type { LaunchableSkill } from "@/lib/types";

// Running a skill, as a dialog: the skill's own frontmatter, and the request
// you're sending. Everything shown here is read off the skill — nothing is
// authored for the launcher, and the skill format gained no fields for it.
//
// Only skills already in your Skills reach this. Running something you haven't
// added would mean adding it for you, which is the user's decision to make.
export default function SkillLauncher({
  skill,
  onClose,
}: {
  skill: LaunchableSkill;
  onClose: () => void;
}) {
  const router = useRouter();
  const openTab = useWorkspace((s) => s.openTab);
  const [request, setRequest] = useState("");

  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") onClose();
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  function run() {
    if (!request.trim()) return;
    const ref = newRunTabRef();
    stageSkillRun(ref, runPrompt(skill.name, request));
    openTab("agent", ref, `Run: ${skill.name}`);
    router.push("/agents");
  }

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/30 p-4"
      onClick={onClose}
    >
      <div
        role="dialog"
        aria-label={`Run ${skill.name}`}
        onClick={(e) => e.stopPropagation()}
        className="w-full max-w-[520px] rounded-xl border border-border bg-base p-5 shadow-xl"
      >
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0">
            <h2 className="m-0 font-display text-[16px] font-bold tracking-tight text-foreground">
              Run {skill.name}
            </h2>
            {skill.description && (
              <p className="m-0 mt-1 text-[12.5px] text-muted-foreground">{skill.description}</p>
            )}
          </div>
          <button
            type="button"
            onClick={onClose}
            aria-label="Close"
            className="cursor-pointer rounded p-1 text-muted-foreground hover:bg-raised hover:text-foreground"
          >
            <X className="h-4 w-4" />
          </button>
        </div>

        {skill.when_to_use && (
          <div className="mt-3 rounded-md border border-border-subtle bg-surface px-3 py-2">
            <p className="m-0 text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">
              When to use
            </p>
            <p className="m-0 mt-1 text-[12.5px] leading-[1.5] text-foreground">
              {skill.when_to_use}
            </p>
          </div>
        )}

        <label
          htmlFor="skill-run-request"
          className="mt-4 block text-[11px] font-semibold uppercase tracking-wide text-muted-foreground"
        >
          Your request
        </label>
        <textarea
          id="skill-run-request"
          value={request}
          onChange={(e) => setRequest(e.target.value)}
          rows={3}
          autoFocus
          placeholder={`What should ${skill.name} do?`}
          className="mt-1.5 w-full resize-y rounded-md border border-border bg-surface px-3 py-2 text-[13px] text-foreground placeholder:text-muted-foreground focus:border-brand focus:outline-none"
        />

        <div className="mt-4 flex items-center justify-end gap-2">
          <button
            type="button"
            onClick={onClose}
            className="cursor-pointer rounded-md border border-border px-3 py-1.5 text-[12.5px] text-foreground hover:bg-raised"
          >
            Cancel
          </button>
          <button
            type="button"
            onClick={run}
            disabled={!request.trim()}
            className="inline-flex cursor-pointer items-center gap-1.5 rounded-md bg-[var(--color-brand-600)] px-3 py-1.5 text-[12.5px] font-medium text-white hover:bg-[var(--color-brand-700)] disabled:opacity-45"
          >
            <Play className="h-3 w-3" />
            Run
          </button>
        </div>
      </div>
    </div>
  );
}
