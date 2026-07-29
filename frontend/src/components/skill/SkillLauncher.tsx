"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { Play, X } from "lucide-react";
import { useWorkspace } from "@/lib/workspace-store";
import {
  ensureInstalled,
  newRunTabRef,
  runPrompt,
  stageSkillRun,
} from "@/lib/skill-launch";
import type { LaunchableSkill } from "@/lib/types";

// Running a skill, as a dialog: what it does, its starter prompts, and the
// request you're actually sending. The prompt stays editable because a skill is
// a procedure, not a button — "brief me" and "brief me on the agent stuff only"
// run the same skill and want different answers.
//
// Run opens a fresh agent chat and sends the prompt for you. Installing first
// is not optional: an agent resolves skills from its own scope, so a Discover
// skill that was never installed would have the agent improvising.
export default function SkillLauncher({
  skill,
  onClose,
}: {
  skill: LaunchableSkill;
  onClose: () => void;
}) {
  const router = useRouter();
  const openTab = useWorkspace((s) => s.openTab);
  const [request, setRequest] = useState(skill.examples[0] ?? "");
  const [starting, setStarting] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") onClose();
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  async function run() {
    if (!request.trim() || starting) return;
    setStarting(true);
    setError("");
    try {
      const name = await ensureInstalled(skill);
      const ref = newRunTabRef();
      stageSkillRun(ref, runPrompt(name, request));
      openTab("agent", ref, `Run: ${name}`);
      router.push("/agents");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not start the run");
      setStarting(false);
    }
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

        {skill.examples.length > 0 && (
          <div className="mt-4">
            <p className="m-0 text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">
              Try
            </p>
            <div className="mt-1.5 flex flex-col gap-1.5">
              {skill.examples.map((example) => (
                <button
                  key={example}
                  type="button"
                  onClick={() => setRequest(example)}
                  className={
                    "cursor-pointer rounded-md border px-2.5 py-1.5 text-left text-[12.5px] transition-colors " +
                    (request === example
                      ? "border-[var(--color-brand-300)] bg-[var(--color-brand-50)] text-[var(--color-brand-700)]"
                      : "border-border bg-surface text-foreground hover:border-[var(--color-brand-300)]")
                  }
                >
                  {example}
                </button>
              ))}
            </div>
          </div>
        )}

        <label className="mt-4 block text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">
          Your request
        </label>
        <textarea
          value={request}
          onChange={(e) => setRequest(e.target.value)}
          rows={3}
          autoFocus
          placeholder={skill.when_to_use || `What should ${skill.name} do?`}
          className="mt-1.5 w-full resize-y rounded-md border border-border bg-surface px-3 py-2 text-[13px] text-foreground placeholder:text-muted-foreground focus:border-brand focus:outline-none"
        />

        {error && <p className="mt-2 text-[12px] text-red-500">{error}</p>}

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
            onClick={() => void run()}
            disabled={!request.trim() || starting}
            className="inline-flex cursor-pointer items-center gap-1.5 rounded-md bg-[var(--color-brand-600)] px-3 py-1.5 text-[12.5px] font-medium text-white hover:bg-[var(--color-brand-700)] disabled:opacity-45"
          >
            <Play className="h-3 w-3" />
            {starting ? "Starting…" : "Run"}
          </button>
        </div>
      </div>
    </div>
  );
}
