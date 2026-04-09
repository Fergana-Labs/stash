/**
 * `openclaw octopus setup` — onboarding wizard.
 * Verifies config, tests auth, sets up workspace and history store.
 */

import type { OctopusClient } from "../octopus-client.js";
import type { OctopusConfig } from "../memory/prompt-section.js";
import { saveState, loadState, saveCache } from "../state.js";

export function createSetupCommand(
  client: OctopusClient,
  config: OctopusConfig,
) {
  return async (args: string[]): Promise<string> => {
    const lines: string[] = [];

    // 1. Check config
    if (!config.apiKey || !config.agentName) {
      return (
        "Missing required config. Set apiKey and agentName in your plugin config:\n" +
        '  plugins.entries["octopus"].config.apiKey = "your-key"\n' +
        '  plugins.entries["octopus"].config.agentName = "your-agent"'
      );
    }

    // 2. Verify auth
    lines.push("Verifying authentication...");
    let profile: Record<string, unknown>;
    try {
      profile = await client.whoami();
      lines.push(`Authenticated as: ${profile.username ?? profile.name ?? "unknown"}`);
    } catch (err) {
      return `Authentication failed: ${err}. Check your apiKey and apiEndpoint.`;
    }

    // 3. Check workspace
    if (config.workspaceId) {
      try {
        const ws = await client.workspaceInfo(config.workspaceId);
        lines.push(`Workspace: ${ws.name} (${config.workspaceId})`);
      } catch {
        lines.push(`Warning: workspace ${config.workspaceId} not found. List workspaces with octopus_list_workspaces.`);
      }
    } else {
      const workspaces = await client.listWorkspaces(true);
      if (workspaces.length > 0) {
        const ws = workspaces[0] as Record<string, unknown>;
        lines.push(
          `No workspace configured. Found ${workspaces.length} workspace(s). ` +
          `Set workspaceId to "${ws.id}" (${ws.name}) or another workspace.`,
        );
      } else {
        lines.push(
          "No workspaces found. Create one with octopus_create_workspace, " +
          "then set workspaceId in your plugin config.",
        );
      }
    }

    // 4. Check history store
    if (config.workspaceId && config.historyStoreId) {
      lines.push(`History store: ${config.historyStoreId}`);

      // Push test event
      try {
        await client.pushEvent({
          workspaceId: config.workspaceId,
          storeId: config.historyStoreId,
          agentName: config.agentName,
          eventType: "session_start",
          content: `OpenClaw plugin connected. Agent: ${config.agentName}`,
        });
        lines.push("Test event pushed successfully.");
      } catch (err) {
        lines.push(`Warning: failed to push test event: ${err}`);
      }

      // Warm cache
      try {
        const events = await client.queryEvents({
          workspaceId: config.workspaceId,
          storeId: config.historyStoreId,
          limit: 20,
        });
        saveCache(profile, events as Record<string, unknown>[]);
        lines.push(`Cache warmed with ${events.length} recent events.`);
      } catch {
        lines.push("Warning: could not warm cache.");
      }
    } else if (config.workspaceId) {
      // Try to create a history store
      try {
        const store = await client.createHistory(
          config.workspaceId,
          `${config.agentName}-activity`,
          `Activity stream for ${config.agentName}`,
        );
        lines.push(
          `Created history store: ${store.name} (${store.id})\n` +
          `Set historyStoreId to "${store.id}" in your plugin config.`,
        );
      } catch {
        lines.push(
          "No history store configured. Create one with octopus_create_memory_store, " +
          "then set historyStoreId in your plugin config.",
        );
      }
    }

    // 5. Initialize state
    const state = loadState();
    state.streaming_enabled = true;
    saveState(state);

    lines.push("");
    lines.push("Setup complete!");
    return lines.join("\n");
  };
}
