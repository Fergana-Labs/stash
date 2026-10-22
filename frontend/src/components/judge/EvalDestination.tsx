"use client";
import { useEffect, useState } from "react";
import JudgeWorkspace from "./JudgeWorkspace";
import EvalDetail from "@/components/evals/judge/EvalDetail";
import { evalGet } from "@/lib/evals-api";

/** Evals made from examples (scored by the judge) open their own page; older evals keep the workspace. */
export default function EvalDestination({ id }: { id: string }) {
  const [judged, setJudged] = useState<boolean | null>(null);
  useEffect(() => {
    let live = true;
    evalGet(id).then(() => live && setJudged(true)).catch(() => live && setJudged(false));
    return () => { live = false; };
  }, [id]);
  if (judged === null) return <p role="status" className="p-6 text-sm text-muted-foreground">Loading eval…</p>;
  return judged ? <EvalDetail id={id} /> : <JudgeWorkspace id={id} />;
}
