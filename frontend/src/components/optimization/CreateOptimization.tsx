"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { Button } from "@/components/ui/button";
import { Field } from "@/components/reward-models/rm-ui";
import TrainSheet from "@/components/reward-models/TrainSheet";
import { errorMessage } from "@/components/reward-models/rm-text";
import { rmListRewardModels } from "@/lib/api";
import { createOptimization, type BusinessMetric } from "@/lib/optimization-api";
import type { RmRewardModel } from "@/lib/types";

export const fieldClass = "w-full rounded-md border border-border bg-background px-3 py-2 text-sm";

export default function CreateOptimization({ initialModelId = "" }: { initialModelId?: string }) {
  const router = useRouter();
  const [models, setModels] = useState<RmRewardModel[]>([]);
  const [modelId, setModelId] = useState(initialModelId);
  const [training, setTraining] = useState(false);
  const [name, setName] = useState("");
  const [agent, setAgent] = useState("codex");
  const [scope, setScope] = useState("");
  const [prompt, setPrompt] = useState("");
  const [metric, setMetric] = useState<BusinessMetric>({ name: "Task accepted", unit: "0 or 1", direction: "higher", minimum: 0, maximum: 1, regression_tolerance: 0 });
  const [runs, setRuns] = useState(20);
  const [rounds, setRounds] = useState(10);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => { void rmListRewardModels().then(setModels).catch((e) => setError(errorMessage(e))); }, []);
  async function start(event: React.FormEvent) {
    event.preventDefault(); setBusy(true); setError(null);
    try {
      const result = await createOptimization({ name: name.trim(), reward_model_id: modelId, agent: agent.trim(), scope: scope.trim(), initial_prompt: prompt, metric, runs_per_arm: runs, max_rounds: rounds });
      router.push(`/reward-models/optimization/${result.id}`);
    } catch (e) { setError(errorMessage(e)); setBusy(false); }
  }
  return <form onSubmit={(event) => void start(event)} className="space-y-6 rounded-xl border border-border bg-background p-6">
    <div><h2 className="m-0 text-lg font-medium">Begin prompt optimization</h2><p className="mb-0 mt-1 text-sm text-muted-foreground">Teach Stash what good work looks like, then improve instructions using future agent runs.</p></div>
    <div className="grid gap-4 md:grid-cols-2">
      <Field label="Name"><input required maxLength={160} className={fieldClass} value={name} onChange={(e) => setName(e.target.value)} placeholder="Support agent improvement" /></Field>
      <Field label="Reward model" hint="Your feedback defines the reward. Training can finish in the background."><select required className={fieldClass} value={modelId} onChange={(e) => setModelId(e.target.value)}><option value="">Choose a reward model</option>{models.filter((m) => m.status !== "failed").map((m) => <option key={m.id} value={m.id}>{m.name}{m.status !== "succeeded" ? ` · ${m.status}` : ""}</option>)}</select><Button type="button" variant="link" className="px-0" onClick={() => setTraining(true)}>Train from my traces and annotations</Button></Field>
      <Field label="Agent" hint="Use the same agent identifier in your MCP calls."><input required maxLength={160} className={fieldClass} value={agent} onChange={(e) => setAgent(e.target.value)} placeholder="codex or support-agent" /></Field>
      <Field label="Scope" hint="The exact project directory or workload identifier this applies to."><input required maxLength={2000} className={fieldClass} value={scope} onChange={(e) => setScope(e.target.value)} placeholder="/projects/my-app or support/refunds" /></Field>
    </div>
    <div className="space-y-4 rounded-lg bg-surface/60 p-4">
      <div><h3 className="m-0 text-sm font-medium">What business result matters?</h3><p className="mb-0 mt-1 text-xs text-muted-foreground">Report an actual measurement for each run. For acceptance, use 1 for accepted and 0 for rejected.</p></div>
      <div className="grid gap-4 md:grid-cols-3">
        <Field label="Business metric"><input required className={fieldClass} value={metric.name} onChange={(e) => setMetric({ ...metric, name: e.target.value })} /></Field>
        <Field label="Units"><input className={fieldClass} value={metric.unit} onChange={(e) => setMetric({ ...metric, unit: e.target.value })} placeholder="minutes, dollars, 0 or 1" /></Field>
        <Field label="Better means"><select className={fieldClass} value={metric.direction} onChange={(e) => setMetric({ ...metric, direction: e.target.value as "higher" | "lower" })}><option value="higher">Higher</option><option value="lower">Lower</option></select></Field>
      </div>
      <div className="grid gap-4 md:grid-cols-3">
        <Field label="Minimum value"><input required type="number" step="any" className={fieldClass} value={metric.minimum} onChange={(e) => setMetric({ ...metric, minimum: Number(e.target.value) })} /></Field>
        <Field label="Maximum value"><input required type="number" step="any" className={fieldClass} value={metric.maximum} onChange={(e) => setMetric({ ...metric, maximum: Number(e.target.value) })} /></Field>
        <Field label="Allowed regression" hint="In metric units. Zero requires no measured regression within the comparison interval."><input required type="number" step="any" min={0} className={fieldClass} value={metric.regression_tolerance} onChange={(e) => setMetric({ ...metric, regression_tolerance: Number(e.target.value) })} /></Field>
      </div>
    </div>
    <details className="rounded-lg border border-border p-4"><summary className="cursor-pointer text-sm font-medium">Current instructions and experiment size</summary><div className="mt-4 space-y-4">
      <Field label="Current supplementary instructions" hint="Leave empty to start from the agent's existing behavior. Existing system instructions and permissions stay in force."><textarea rows={5} maxLength={12000} className={fieldClass} value={prompt} onChange={(e) => setPrompt(e.target.value)} /></Field>
      <div className="grid gap-4 md:grid-cols-2"><Field label="Runs per prompt per round"><input required type="number" min={5} max={500} className={fieldClass} value={runs} onChange={(e) => setRuns(Number(e.target.value))} /></Field><Field label="Maximum rounds"><input required type="number" min={1} max={100} className={fieldClass} value={rounds} onChange={(e) => setRounds(Number(e.target.value))} /></Field></div>
    </div></details>
    <p className="text-xs leading-relaxed text-muted-foreground">Starting enables candidate generation, remote reward scoring, and prompt experiments on connected future tasks. Each round compares {runs} current-prompt runs with {runs} candidate runs. A candidate becomes current only when reward improves and the business guardrail passes. Pause or roll back at any time.</p>
    {error && <p role="alert" className="text-sm text-red-600">{error}</p>}
    <Button type="submit" disabled={busy || !modelId}>{busy ? "Starting…" : "Begin prompt optimization"}</Button>
    <TrainSheet open={training} onOpenChange={setTraining} onTrained={(model) => { setTraining(false); setModels((all) => [model, ...all]); setModelId(model.id); }} />
  </form>;
}
