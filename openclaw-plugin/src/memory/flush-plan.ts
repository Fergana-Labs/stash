/**
 * Memory flush plan resolver — controls when memories are persisted to Octopus.
 * Registered via api.registerMemoryFlushPlan().
 *
 * OpenClaw SDK signature:
 *   (params: { cfg?: OpenClawConfig; nowMs?: number }) => MemoryFlushPlan | null
 *
 * MemoryFlushPlan = { softThresholdTokens: number; ... }
 */

import type { OctopusClient } from "../octopus-client.js";
import type { OctopusConfig } from "./prompt-section.js";

/**
 * Creates the flush plan resolver for Octopus memory persistence.
 * Returns a MemoryFlushPlan that triggers flush at a reasonable token threshold.
 */
export function createFlushPlanResolver(_client: OctopusClient, _config: OctopusConfig) {
  return (_params: { cfg?: unknown; nowMs?: number }) => {
    return {
      softThresholdTokens: 50_000,
      forceFlushTranscriptBytes: 200_000,
      reserveTokensFloor: 2_000,
      prompt: "Summarize the session so far for future context.",
      systemPrompt: "You are summarizing an AI agent session for memory persistence.",
      relativePath: ".octopus/memory",
    };
  };
}
