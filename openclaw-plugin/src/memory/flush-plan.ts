/**
 * Memory flush plan — controls when memories are persisted to Boozle.
 * Registered via api.registerMemoryFlushPlan().
 *
 * Handles session end summaries (port of on_stop.py).
 */

import type { BoozleClient } from "../boozle-client.js";
import type { BoozleConfig } from "./prompt-section.js";
import { loadState, saveState } from "../state.js";

/**
 * Creates the flush plan resolver for Boozle memory persistence.
 */
export function createFlushPlan(client: BoozleClient, config: BoozleConfig) {
  return {
    /**
     * Called on session end — push a summary event to Boozle history.
     */
    async flush(sessionData?: {
      toolCount?: number;
      filesChanged?: string[];
      toolsUsed?: string[];
    }) {
      const state = loadState();
      if (!state.streaming_enabled) return;
      if (!config.workspaceId || !config.historyStoreId) return;

      const toolCount = sessionData?.toolCount ?? 0;
      const filesChanged = sessionData?.filesChanged ?? [];
      const toolsUsed = sessionData?.toolsUsed ?? [];

      const parts = ["Session ended."];
      if (toolCount) parts.push(`${toolCount} tool uses.`);
      if (filesChanged.length) {
        parts.push(`${filesChanged.length} files changed.`);
      }
      const content = parts.join(" ");

      try {
        await client.pushEvent({
          workspaceId: config.workspaceId,
          storeId: config.historyStoreId,
          agentName: config.agentName,
          eventType: "session_end",
          content,
          sessionId: state.session_id,
          metadata: {
            tool_count: toolCount,
            files_changed: filesChanged,
            tools_used: toolsUsed,
          },
        });
      } catch {
        // Server unreachable — event is lost
      }

      // Clear session ID
      state.session_id = "";
      saveState(state);
    },
  };
}
