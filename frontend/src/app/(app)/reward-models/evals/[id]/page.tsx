import Link from "next/link";
import EvalWorkspace from "@/components/evals/EvalWorkspace";
import { RmPage } from "@/components/reward-models/rm-ui";

export default async function EvalPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  return <RmPage title="Eval builder" wide actions={<Link href="/reward-models/evals" className="text-xs text-muted-foreground hover:underline">Back to evals</Link>}><EvalWorkspace key={id} id={id} /></RmPage>;
}
