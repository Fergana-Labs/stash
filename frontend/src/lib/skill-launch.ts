// Running a skill: the launcher opens a fresh agent chat tab and the tab sends
// the prompt on mount. The prompt is staged here rather than passed through the
// URL because a run prompt is prose — it carries newlines and quoting that a
// query string mangles — and because a stale prompt in the address bar would
// re-run the skill on every reload. One-shot, like the agent config-view intent.

import { installSkill } from "@/lib/api";
import type { LaunchableSkill } from "@/lib/types";

const pending = new Map<string, string>();

export function stageSkillRun(tabRef: string, prompt: string): void {
  pending.set(tabRef, prompt);
}

export function takeSkillRun(tabRef: string): string | null {
  const prompt = pending.get(tabRef) ?? null;
  pending.delete(tabRef);
  return prompt;
}

/** The tab id for a run. Every launch gets its own chat: a skill run is a piece
 *  of work with an output, not a message in an ongoing conversation. */
export function newRunTabRef(): string {
  return `new-run-${Math.random().toString(36).slice(2, 10)}`;
}

/** What we send the agent. Naming the skill is the whole mechanism — the agent
 *  resolves it with read_skill and follows it — so the instruction leads with
 *  the name and the user's request follows it. */
export function runPrompt(skillName: string, request: string): string {
  return `Use the ${skillName} skill.\n\n${request.trim()}`;
}

/** Put the skill in the caller's scope if it isn't already, then return the
 *  name to invoke. Published skills live in the service account until someone
 *  installs them, and an agent only sees its own scope. */
export async function ensureInstalled(skill: LaunchableSkill): Promise<string> {
  if (!skill.slug) return skill.name;
  const installed = await installSkill(skill.slug);
  return installed.name;
}
