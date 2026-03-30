/**
 * Memory prompt section builder — injects scored context from Boozle injection API.
 * Port of claude-plugin/scripts/on_prompt.py.
 *
 * Registered via api.registerMemoryPromptSection().
 * OpenClaw SDK signature: (params: { availableTools: Set<string>; citationsMode?: ... }) => string[]
 */

import type { BoozleClient } from "../boozle-client.js";
import {
  loadState,
  loadCache,
  loadInjectionState,
  saveInjectionState,
} from "../state.js";

export interface BoozleConfig {
  apiEndpoint: string;
  apiKey: string;
  agentName: string;
  workspaceId?: string;
  historyStoreId?: string;
}

function buildFallbackContext(
  agentName: string,
  persona: string,
  recentEvents: Record<string, unknown>[],
): string[] {
  const lines: string[] = [];
  lines.push("## Agent Identity");
  lines.push(`You are **${agentName}**, a Boozle agent.`);
  if (persona) lines.push(persona);
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
 * Creates the prompt section builder function for Boozle memory injection.
 * Returns string[] (one line per element) per OpenClaw SDK contract.
 */
export function createPromptSectionBuilder(
  client: BoozleClient,
  config: BoozleConfig,
) {
  let cachedLines: string[] = [];
  let lastFetchMs = 0;
  const CACHE_TTL_MS = 30_000;

  void prefetch();

  async function prefetch() {
    const state = loadState();
    let injectionState = loadInjectionState();
    const sessionId = state.session_id;

    try {
      const result = await client.inject({
        promptText: ".",
        sessionState: injectionState as unknown as Record<string, unknown>,
        sessionId,
      });
      const context = result.context ?? "";
      cachedLines = context.split("\n");
      const updatedState = result.updated_session_state ?? injectionState;
      saveInjectionState(updatedState as unknown as typeof injectionState);
      lastFetchMs = Date.now();
    } catch {
      const cache = loadCache();
      let persona = state.persona;
      if (!persona && cache?.profile) {
        persona = String(cache.profile.description ?? "");
      }
      const recentEvents = cache?.recent_events ?? [];
      cachedLines = buildFallbackContext(config.agentName, persona, recentEvents);
      lastFetchMs = Date.now();
    }
  }

  return (_params: { availableTools: Set<string> }): string[] => {
    if (Date.now() - lastFetchMs > CACHE_TTL_MS) {
      void prefetch();
    }
    return cachedLines;
  };
}
