"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { rmCreateGepaRun, rmListGepaRuns } from "@/lib/api";
import { errorMessage } from "./rm-text";

export default function ViewSkillButton({ modelId }: { modelId: string }) {
  const router = useRouter();
  const [opening, setOpening] = useState(false);

  async function open() {
    setOpening(true);
    try {
      const runs = await rmListGepaRuns();
      let run = runs.find((candidate) => candidate.reward_model_id === modelId);
      if (!run) run = await rmCreateGepaRun({ reward_model_id: modelId });
      router.push(`/reward-models/gepa/${run.id}`);
    } catch (e) {
      toast.error(errorMessage(e));
      setOpening(false);
    }
  }

  return <Button size="xs" onClick={() => void open()} disabled={opening}>{opening ? "Opening…" : "View skill"}</Button>;
}
