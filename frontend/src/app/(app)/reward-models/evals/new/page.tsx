"use client";

import { EvalPageFrame } from "@/components/evals/eval-ui";
import NewEvalUpload from "@/components/evals/judge/NewEvalUpload";

/** New eval: drop examples of good work; that's all it needs. */
export default function NewEvalPage() {
  return (
    <EvalPageFrame title="New eval" description="Show it examples of good work. It gives your agents an endpoint that scores theirs.">
      <NewEvalUpload />
    </EvalPageFrame>
  );
}
