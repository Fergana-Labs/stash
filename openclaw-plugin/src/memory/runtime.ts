/**
 * Memory runtime adapter — Octopus history as the storage backend.
 * Registered via api.registerMemoryRuntime().
 *
 * Bridges OpenClaw's memory interface to Octopus's REST API for
 * storing, retrieving, and searching memory events.
 */

import type { OctopusClient } from "../octopus-client.js";
import type { OctopusConfig } from "./prompt-section.js";
import { loadState } from "../state.js";

/**
 * Creates the memory runtime adapter backed by Octopus's history store.
 */
export function createMemoryRuntime(
  client: OctopusClient,
  config: OctopusConfig,
) {
  return {
    /** Store a memory entry in Octopus history. */
    async store(content: string, metadata?: Record<string, unknown>) {
      if (!config.workspaceId || !config.historyStoreId) return;
      const state = loadState();
      await client.pushEvent({
        workspaceId: config.workspaceId,
        storeId: config.historyStoreId,
        agentName: config.agentName,
        eventType: metadata?.event_type as string ?? "memory",
        content,
        sessionId: state.session_id,
        metadata,
      });
    },

    /** Retrieve recent memory entries from Octopus history. */
    async retrieve(limit = 20): Promise<unknown[]> {
      if (!config.workspaceId || !config.historyStoreId) return [];
      return client.queryEvents({
        workspaceId: config.workspaceId,
        storeId: config.historyStoreId,
        limit,
      });
    },

    /** Search memory entries using full-text search. */
    async search(query: string, limit = 20): Promise<unknown[]> {
      if (!config.workspaceId || !config.historyStoreId) return [];
      return client.searchEvents(
        config.workspaceId,
        config.historyStoreId,
        query,
        limit,
      );
    },
  };
}
