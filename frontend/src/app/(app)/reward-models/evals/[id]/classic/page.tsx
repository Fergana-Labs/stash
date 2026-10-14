import Link from "next/link";
import { EvalPageFrame } from "@/components/evals/eval-ui";
import EvalWorkspace from "@/components/evals/EvalWorkspace";

/** The previous eval workspace, kept reachable while the judge page settles. */
export default async function ClassicEvalPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  return <EvalPageFrame><Link href={`/reward-models/evals/${id}`} className="text-xs text-muted-foreground hover:underline">Back to the eval /</Link><EvalWorkspace key={id} id={id} /></EvalPageFrame>;
}
