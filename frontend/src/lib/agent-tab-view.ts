// One-shot intent to open an agent tab on its Config view instead of Chat.
// The Agents explorer sets it right before opening the tab; the agent tab reads
// (and clears) it once on mount. Chat and Config are one tab with a selector,
// so the gear and "new agent" just preselect the Config side of that tab.

const pending = new Set<string>();

export function requestAgentConfigView(agentId: string): void {
  pending.add(agentId);
}

export function takeAgentConfigView(agentId: string): boolean {
  return pending.delete(agentId);
}
