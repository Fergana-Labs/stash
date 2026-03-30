/**
 * Memory prompt section builder — injects scored context from Boozle injection API.
 * Port of claude-plugin/scripts/on_prompt.py.
 *
 * Registered via api.registerMemoryPromptSection().
 * Called before each prompt to build the memory context to inject.
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
): string {
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

  return lines.join("\n");
}

/**
 * Creates the prompt section builder function for Boozle memory injection.
 */
export function createPromptSectionBuilder(
  client: BoozleClient,
  config: BoozleConfig,
) {
  return async (promptText?: string): Promise<string> => {
    const state = loadState();
    let injectionState = loadInjectionState();
    const sessionId = state.session_id;

    let context: string | null = null;

    // --- Cloud path: call injection endpoint ---
    try {
      const result = await client.inject({
        promptText: promptText || ".",
        sessionState: injectionState as unknown as Record<string, unknown>,
        sessionId,
      });
      context = result.context ?? "";
      const updatedState = result.updated_session_state ?? injectionState;
      saveInjectionState(updatedState as unknown as typeof injectionState);
    } catch {
      // API unreachable — fall through to cached fallback
    }

    // --- Cached fallback ---
    if (context === null) {
      const cache = loadCache();
      let persona = state.persona;
      if (!persona && cache?.profile) {
        persona = String(cache.profile.description ?? "");
      }
      const recentEvents = cache?.recent_events ?? [];
      context = buildFallbackContext(
        config.agentName,
        persona,
        recentEvents,
      );

      // Increment prompt_num locally
      injectionState.prompt_num = (injectionState.prompt_num ?? 0) + 1;
      saveInjectionState(injectionState);
    }

    return context;
  };
}
