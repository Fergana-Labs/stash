import Link from "next/link";
import { EvalPageFrame } from "@/components/evals/eval-ui";
import EvalWorkspace from "@/components/evals/EvalWorkspace";

export default async function EvalPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  return <EvalPageFrame><Link href="/reward-models/evals" className="text-xs text-muted-foreground hover:underline">Evals /</Link><EvalWorkspace key={id} id={id} /></EvalPageFrame>;
}
