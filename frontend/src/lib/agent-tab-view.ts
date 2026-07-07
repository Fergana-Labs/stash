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

// Same one-shot pattern for the Memory explorer's "Curate wiki" button: it
// opens the curator's config tab, which reads (and clears) this to auto-start
// a run. There is one curator per account, so no id key is needed.
let curatorRunPending = false;

export function requestCuratorRun(): void {
  curatorRunPending = true;
}

export function takeCuratorRun(): boolean {
  const was = curatorRunPending;
  curatorRunPending = false;
  return was;
}
