/**
 * Memory prompt section builder — injects agent identity + recent activity
 * from the local context cache populated by the sync loop.
 *
 * Registered via api.registerMemoryPromptSection().
 * OpenClaw SDK signature: (params: { availableTools: Set<string>; citationsMode?: ... }) => string[]
 */

import type { OctopusClient } from "../octopus-client.js";
import { loadCache } from "../state.js";

export interface OctopusConfig {
  apiEndpoint: string;
  apiKey: string;
  agentName: string;
  workspaceId?: string;
  historyStoreId?: string;
}

function buildContext(
  agentName: string,
  description: string,
  recentEvents: Record<string, unknown>[],
): string[] {
  const lines: string[] = [];
  lines.push("## Agent Identity");
  lines.push(`You are **${agentName}**, a Octopus agent.`);
  if (description) lines.push(description);
  lines.push("");

  if (recentEvents.length > 0) {
    lines.push("## Recent Activity (your previous sessions)");
    for (const event of recentEvents.slice(0, 15)) {
      const ts = String(event.created_at ?? "").slice(0, 16);
      const tool = event.tool_name ?? "";
      const content = String(event.content ?? "").slice(0, 200);
      const eventType = event.event_type ?? "";
      if (tool) {
        lines.push(`- [${ts}] ${tool}: ${content}`);
      } else {
        lines.push(`- [${ts}] (${eventType}) ${content}`);
      }
    }
    lines.push("");
  }

  return lines;
}

/**
 * Creates the prompt section builder function for Octopus memory injection.
 * Returns string[] (one line per element) per OpenClaw SDK contract.
 */
export function createPromptSectionBuilder(
  _client: OctopusClient,
  config: OctopusConfig,
) {
  let cachedLines: string[] = [];
  let lastFetchMs = 0;
  const CACHE_TTL_MS = 30_000;

  void refresh();

  function refresh() {
    const cache = loadCache();
    const description = String(cache?.profile?.description ?? "");
    const recentEvents = cache?.recent_events ?? [];
    cachedLines = buildContext(config.agentName, description, recentEvents);
    lastFetchMs = Date.now();
  }

  return (_params: { availableTools: Set<string> }): string[] => {
    if (Date.now() - lastFetchMs > CACHE_TTL_MS) {
      refresh();
    }
    return cachedLines;
  };
}
