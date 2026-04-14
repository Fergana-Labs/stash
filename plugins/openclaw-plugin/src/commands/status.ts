/**
 * `openclaw octopus status` — display connection status.
 */

import type { OctopusClient } from "../octopus-client.js";
import type { OctopusConfig } from "../memory/prompt-section.js";
import { loadState, loadCache } from "../state.js";

export function createStatusCommand(
  client: OctopusClient,
  config: OctopusConfig,
) {
  return async (): Promise<string> => {
    const state = loadState();
    const cache = loadCache();
    const lines: string[] = [];

    lines.push("=== Octopus Plugin Status ===");
    lines.push("");
    lines.push(`Agent:       ${config.agentName || "(not set)"}`);
    lines.push(`Endpoint:    ${config.apiEndpoint}`);
    lines.push(`Workspace:   ${config.workspaceId || "(not set)"}`);
    lines.push(`History:     ${config.historyStoreId || "(not set)"}`);
    lines.push(`Streaming:   ${state.streaming_enabled ? "enabled" : "paused"}`);
    lines.push(`Agent Name:  ${state.persona || "(default)"}`);
    lines.push(`Session:     ${state.session_id || "(none)"}`);
    lines.push(`Cache:       ${cache ? "fresh" : "stale/empty"}`);

    // Connection check
    try {
      const profile = await client.whoami();
      lines.push(`Connection:  OK (${profile.username ?? profile.name})`);
    } catch (err) {
      lines.push(`Connection:  FAILED (${err})`);
    }

    return lines.join("\n");
  };
}
