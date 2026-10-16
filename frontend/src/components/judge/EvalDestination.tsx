"use client";
import { useEffect, useState } from "react";
import JudgeWorkspace from "./JudgeWorkspace";
import WebsiteEvalCard from "@/components/wizard/cards/WebsiteEvalCard";
import { tasteGet, type TasteWorkspace } from "@/lib/taste-api";
import { EvalPageFrame } from "@/components/evals/eval-ui";
export default function EvalDestination({ id }: { id: string }) {
  const [website, setWebsite] = useState<TasteWorkspace | null | undefined>(
    undefined,
  );
  useEffect(() => {
    let active = true;
    void tasteGet()
      .then((value) => {
        if (active) setWebsite(value);
      })
      .catch(() => {
        if (active) setWebsite(null);
      });
    return () => {
      active = false;
    };
  }, [id]);
  if (website === undefined)
    return (
      <p role="status" className="p-6 text-sm">
        Loading eval…
      </p>
    );
  if (website?.model_id !== id) return <JudgeWorkspace id={id} />;
  return (
    <EvalPageFrame
      title={website.name}
      description="Your learned judgment, its evidence and agent results."
    >
      <div className="mx-auto max-w-4xl">
        <WebsiteEvalCard section="grader" readOnly />
        <WebsiteEvalCard section="connect" readOnly />
        <WebsiteEvalCard section="results" readOnly />
      </div>
    </EvalPageFrame>
  );
}
