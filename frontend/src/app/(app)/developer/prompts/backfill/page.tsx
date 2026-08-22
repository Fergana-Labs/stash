"use client";

import PromptPage from "@/components/developer/PromptPage";
import { BACKFILL_PROMPT } from "@/components/developer/agentPrompts";

export default function BackfillPromptRoute() {
  return (
    <PromptPage
      title="Backfill"
      blurb="You already have months of conversations in your own database. This prompt has
        your coding agent write the one-time script that uploads them — original
        timestamps, resumable, batched — and ends with pressing Backfill on the Curator
        page so the wikis build from day one."
      prompt={BACKFILL_PROMPT}
    />
  );
}
