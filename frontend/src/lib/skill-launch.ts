// Running a skill: the launcher opens a fresh agent chat tab and the tab sends
// the prompt on mount. The prompt is staged here rather than passed through the
// URL because a run prompt is prose — it carries newlines and quoting that a
// query string mangles — and because a stale prompt in the address bar would
// re-run the skill on every reload. One-shot, like the agent config-view intent.

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

/** What we send. The agent picks skills by matching your message against each
 *  skill's when_to_use, which makes an unaided run a guess — naming the skill
 *  is what makes Run mean *this* skill. That's the whole of what we compose:
 *  one line off the skill's name, and then your words. Nothing is authored per
 *  skill, and the skill's own SKILL.md says what to do once it's loaded. */
export function runPrompt(skillName: string, request: string): string {
  return `Use the ${skillName} skill.\n\n${request.trim()}`;
}
