"use client";

import { useProductCheckpoint } from "@/components/ProductCheckpointContext";
import LegacyRewardModels from "@/components/reward-models/LegacyRewardModels";
import EvalsPage from "../evals/page";

/** Bookmarked model-list URLs enter the new eval flow; pinned snapshots retain their view. */
export default function ModelsPage() {
  return useProductCheckpoint() === "floodgate-2026-10-05" ? <LegacyRewardModels /> : <EvalsPage />;
}
