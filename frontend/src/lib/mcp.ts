/**
 * Client for the workspace MCP proxy: curated provider presets (Render, …)
 * that agents reach through Stash with read-only tool allowlists. Humans
 * connect here; agents consume via the CLI / MCP endpoint.
 */

import { apiFetch } from "./api";

export type McpPreset = {
  name: string;
  label: string;
  url: string;
  key_help: string;
  tool_allowlist: string[];
  connected: boolean;
};

export async function listMcpPresets(workspaceId: string): Promise<{ presets: McpPreset[] }> {
  return apiFetch(`/api/v1/workspaces/${workspaceId}/mcp-presets`);
}

export async function connectMcpPreset(
  workspaceId: string,
  preset: string,
  apiKey: string
): Promise<void> {
  await apiFetch(`/api/v1/workspaces/${workspaceId}/mcp-presets/${preset}/connect`, {
    method: "POST",
    body: JSON.stringify({ api_key: apiKey }),
  });
}

export async function disconnectMcpServer(workspaceId: string, name: string): Promise<void> {
  await apiFetch(`/api/v1/workspaces/${workspaceId}/mcp-servers/${name}`, {
    method: "DELETE",
  });
}
