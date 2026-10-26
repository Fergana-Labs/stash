"use client";

import { EvalPageFrame } from "@/components/evals/eval-ui";
import NewEvalChannel, { SetUpInChat } from "@/components/evals/judge/NewEvalChannel";

/** New eval: drop in examples of the agent's work and say what you think of them, or set it
 * up in a conversation with the wizard. */
export default function NewEvalPage() {
  return (
    <EvalPageFrame title="New eval" actions={<SetUpInChat />}>
      <NewEvalChannel />
    </EvalPageFrame>
  );
}
