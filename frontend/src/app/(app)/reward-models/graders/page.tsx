import Link from "next/link";

export default function EvaluationInfo() {
  return <div className="mx-auto max-w-3xl space-y-4 p-8"><h1 className="text-xl font-medium">Evaluation is automatic</h1><p>Jev always answers two questions: was the trace successful, and how much credit does each action deserve?</p><p>Stash uses the recorded requests, applicable instructions, actions and later results. No grader, rubric or model selection is required.</p><Link href="/reward-models" className="underline">Open your traces →</Link><details className="pt-6"><summary className="cursor-pointer text-sm text-muted-foreground">Earlier rubric configurations</summary><p className="text-sm text-muted-foreground">Historical records and research endpoints are retained. They do not configure automatic trace evaluation.</p></details></div>;
}
