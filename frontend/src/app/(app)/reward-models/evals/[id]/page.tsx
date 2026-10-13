import Link from "next/link";
import EvalWorkspace from "@/components/evals/EvalWorkspace";

export default async function EvalPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  return <div className="scroll-thin h-full overflow-y-auto"><div className="mx-auto max-w-7xl px-10 pt-7 pb-16"><Link href="/reward-models/evals" className="text-xs text-muted-foreground hover:underline">← Back to evals</Link><EvalWorkspace key={id} id={id} /></div></div>;
}
