/**
 * `openclaw boozle status` — display connection status.
 */

import type { BoozleClient } from "../boozle-client.js";
import type { BoozleConfig } from "../memory/prompt-section.js";
import { loadState, loadCache } from "../state.js";

export function createStatusCommand(
  client: BoozleClient,
  config: BoozleConfig,
) {
  return async (): Promise<string> => {
    const state = loadState();
    const cache = loadCache();
    const lines: string[] = [];

    lines.push("=== Boozle Plugin Status ===");
    lines.push("");
    lines.push(`Agent:       ${config.agentName || "(not set)"}`);
    lines.push(`Endpoint:    ${config.apiEndpoint}`);
    lines.push(`Workspace:   ${config.workspaceId || "(not set)"}`);
    lines.push(`History:     ${config.historyStoreId || "(not set)"}`);
    lines.push(`Streaming:   ${state.streaming_enabled ? "enabled" : "paused"}`);
    lines.push(`Persona:     ${state.persona || "(default)"}`);
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
