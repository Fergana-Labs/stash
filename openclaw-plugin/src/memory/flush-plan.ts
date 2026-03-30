/**
 * Memory flush plan resolver — controls when memories are persisted to Boozle.
 * Registered via api.registerMemoryFlushPlan().
 *
 * OpenClaw SDK signature:
 *   (params: { cfg?: OpenClawConfig; nowMs?: number }) => MemoryFlushPlan | null
 *
 * MemoryFlushPlan = { softThresholdTokens: number; ... }
 */

import type { BoozleClient } from "../boozle-client.js";
import type { BoozleConfig } from "./prompt-section.js";

/**
 * Creates the flush plan resolver for Boozle memory persistence.
 * Returns a MemoryFlushPlan that triggers flush at a reasonable token threshold.
 */
export function createFlushPlanResolver(_client: BoozleClient, _config: BoozleConfig) {
  return (_params: { cfg?: unknown; nowMs?: number }) => {
    return {
      softThresholdTokens: 50_000,
      forceFlushTranscriptBytes: 200_000,
      reserveTokensFloor: 2_000,
      prompt: "Summarize the session so far for future context.",
      systemPrompt: "You are summarizing an AI agent session for memory persistence.",
      relativePath: ".boozle/memory",
    };
  };
}
