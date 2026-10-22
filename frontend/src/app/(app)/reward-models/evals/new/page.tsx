"use client";

import { EvalPageFrame } from "@/components/evals/eval-ui";
import NewEvalUpload from "@/components/evals/judge/NewEvalUpload";

/** New eval: drop examples of good work; that's all it needs. */
export default function NewEvalPage() {
  return (
    <EvalPageFrame title="New eval" description="Drop in the examples you want to use to create your verifier.">
      <NewEvalUpload />
    </EvalPageFrame>
  );
}
