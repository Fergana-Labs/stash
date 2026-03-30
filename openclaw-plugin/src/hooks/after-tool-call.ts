/**
 * After-tool-call hook — stream tool activity to Boozle history.
 * Port of claude-plugin/scripts/on_tool_use.py.
 */

import type { BoozleClient } from "../boozle-client.js";
import type { BoozleConfig } from "../memory/prompt-section.js";
import { loadState } from "../state.js";

const EXCLUDED_TOOLS = new Set([
  "Read",
  "Glob",
  "Grep",
  "ToolSearch",
  "memory_search",
  "memory_get",
]);

function summarizeToolUse(
  toolName: string,
  toolInput: Record<string, unknown>,
): { content: string; metadata: Record<string, unknown> } {
  let content: string;
  let metadata: Record<string, unknown> = {};

  switch (toolName) {
    case "Edit": {
      const filePath = String(toolInput.file_path ?? "unknown");
      const old = String(toolInput.old_string ?? "").slice(0, 100);
      const newStr = String(toolInput.new_string ?? "").slice(0, 100);
      content = `Edited ${filePath}`;
      metadata = { file_path: filePath, old_preview: old, new_preview: newStr };
      break;
    }
    case "Write": {
      const filePath = String(toolInput.file_path ?? "unknown");
      content = `Created/wrote ${filePath}`;
      metadata = { file_path: filePath };
      break;
    }
    case "Bash": {
      const command = String(toolInput.command ?? "").slice(0, 300);
      content = `Ran: ${command}`;
      metadata = { command };
      break;
    }
    case "Agent": {
      const desc = String(
        toolInput.description ?? toolInput.prompt ?? "",
      ).slice(0, 200);
      content = `Launched agent: ${desc}`;
      metadata = { subagent_type: String(toolInput.subagent_type ?? "") };
      break;
    }
    default: {
      content = `${toolName}: ${JSON.stringify(toolInput).slice(0, 200)}`;
      metadata = { tool_input_preview: JSON.stringify(toolInput).slice(0, 500) };
    }
  }

  return { content, metadata };
}

/**
 * Creates the after-tool-call hook handler.
 */
export function createAfterToolCallHook(
  client: BoozleClient,
  config: BoozleConfig,
) {
  return async (data: {
    tool_name?: string;
    tool_input?: Record<string, unknown>;
    cwd?: string;
  }) => {
    const toolName = data.tool_name ?? "";
    if (!toolName || EXCLUDED_TOOLS.has(toolName)) return { block: false };

    const state = loadState();
    if (!state.streaming_enabled) return { block: false };
    if (!config.workspaceId || !config.historyStoreId) return { block: false };

    const toolInput =
      typeof data.tool_input === "string"
        ? { raw: data.tool_input }
        : (data.tool_input ?? {});

    const { content, metadata } = summarizeToolUse(toolName, toolInput);
    metadata.cwd = data.cwd ?? "";

    // Fire-and-forget — don't block the agent
    client
      .pushEvent({
        workspaceId: config.workspaceId,
        storeId: config.historyStoreId,
        agentName: config.agentName,
        eventType: "tool_use",
        content,
        sessionId: state.session_id,
        toolName,
        metadata,
      })
      .catch(() => {
        // Server unreachable — event is lost
      });

    return { block: false };
  };
}
