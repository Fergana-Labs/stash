"use client";

import { useState } from "react";
import { setSkillAgentEnabled, type Skill } from "@/lib/api";
import { cn } from "@/lib/utils";

/** The switch that hands a Skill to the user's coding agents (or takes it
 *  back). Shared by the Skills list and the Skill page. */
export default function SkillEnabledToggle({
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
