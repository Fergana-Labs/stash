"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { Button } from "@/components/ui/button";
import { Field } from "@/components/reward-models/rm-ui";
import { errorMessage } from "@/components/reward-models/rm-text";
import { rmListRewardModels } from "@/lib/api";
import { createOptimization } from "@/lib/optimization-api";
import { imGet, imList, type ModelSummary } from "@/lib/intuition-api";
import type { RmRewardModel } from "@/lib/types";

export const fieldClass = "w-full rounded-md border border-border bg-background px-3 py-2 text-sm";

export default function CreateOptimization({ initialModelId = "", initialAgent = "" }: { initialModelId?: string; initialAgent?: string }) {
  const router = useRouter();
  const [models, setModels] = useState<RmRewardModel[] | null>(null);
  // "rm:<id>" scores runs with a reward model; "eval:<id>" with an eval's decision.
  const [selectedModel, setModel] = useState(initialModelId ? `rm:${initialModelId}` : "");
  const [evals, setEvals] = useState<ModelSummary[]>([]);
  const [decisions, setDecisions] = useState<string[]>([]);
  const [target, setTarget] = useState("");
  const [name, setName] = useState("");
  const [agent, setAgent] = useState(initialAgent);
  const [scope, setScope] = useState("");
  const [prompt, setPrompt] = useState("");
  const [runs, setRuns] = useState(20);
  const [rounds, setRounds] = useState(10);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => { void rmListRewardModels().then(setModels).catch((e) => setError(errorMessage(e))); }, []);
  useEffect(() => { void imList().then((r) => setEvals(r.models.filter((m) => m.active_version_id))).catch(() => setEvals([])); }, []);
  const available = models?.filter((m) => m.status === "succeeded" && m.metrics?.action_scoring_version === 1) ?? [];
  const [kind, chosenId] = selectedModel.split(":") as ["rm" | "eval" | "", string | undefined];
  const modelId = kind === "rm" && available.some((m) => m.id === chosenId) ? chosenId! : "";
  const evalId = kind === "eval" && evals.some((e) => e.id === chosenId) ? chosenId! : "";
  const model = available.find((m) => m.id === modelId);
  const chosenEval = evals.find((e) => e.id === evalId);
  const scorer = model?.name ?? chosenEval?.name;
  useEffect(() => {
    if (!evalId) { setDecisions([]); setTarget(""); return; }
    void imGet(evalId).then((d) => {
      const options = d.model.output_type === "choice" ? d.active?.labels.map((l) => l.id) ?? [] : ["good", "bad"];
      setDecisions(options); setTarget(options[0] ?? "");
    }).catch((e) => setError(errorMessage(e)));
  }, [evalId]);
  async function start(event: React.FormEvent) {
    event.preventDefault(); setBusy(true); setError(null);
    try {
      const result = await createOptimization({ name: name.trim() || `${agent.trim()}, ${scorer}`.slice(0, 160), ...(evalId ? { eval_id: evalId, target_label: target } : { reward_model_id: modelId }), agent: agent.trim(), scope: scope.trim() || "default", initial_prompt: prompt, runs_per_arm: runs, max_rounds: rounds });
      router.push(`/reward-models/optimization/${result.id}`);
    } catch (e) { setError(errorMessage(e)); setBusy(false); }
  }
  return <form onSubmit={(event) => void start(event)} className="space-y-4 border-y border-border py-4">
    <div><h2 className="m-0 text-sm font-medium text-foreground">Optimize {initialAgent || "an agent"}</h2><p className="mb-0 mt-1 text-xs text-muted-foreground">Improve the prompt using scores from a reward model or an eval.</p></div>
    <div className="flex flex-wrap items-end gap-3">
      {!initialAgent && <div className="min-w-48 flex-1"><Field label="Agent"><input required maxLength={160} className={fieldClass} value={agent} onChange={(e) => setAgent(e.target.value)} placeholder="Agent name" /></Field></div>}
      <div className="min-w-56 flex-1"><Field label="Score runs with"><select required aria-label="Reward model or eval to optimize against" disabled={busy || models === null} className={fieldClass} value={modelId || evalId ? selectedModel : ""} onChange={(e) => setModel(e.target.value)}><option value="">{models === null ? "Loading…" : "Choose a reward model or eval"}</option>{!!available.length && <optgroup label="Reward models">{available.map((m) => <option key={m.id} value={`rm:${m.id}`}>{m.name}</option>)}</optgroup>}{!!evals.length && <optgroup label="Evals">{evals.map((e) => <option key={e.id} value={`eval:${e.id}`}>{e.name}</option>)}</optgroup>}</select></Field></div>
      {evalId && <div className="min-w-40"><Field label="Success is"><select aria-label="Decision that counts as success" className={fieldClass} value={target} onChange={(e) => setTarget(e.target.value)}>{decisions.map((d) => <option key={d} value={d}>{d}</option>)}</select></Field></div>}
      <Button type="submit" disabled={busy || !(modelId || (evalId && target)) || !agent.trim()}>{busy ? "Starting…" : "Start optimization"}</Button>
    </div>
    {models && !available.length && !evals.length && <p className="text-xs text-muted-foreground">A ready action reward model or a saved eval is needed to optimize this agent.</p>}
    <details className="text-xs"><summary className="cursor-pointer text-muted-foreground">Optional settings</summary><div className="mt-3 space-y-3">
      <Field label="Current prompt"><textarea rows={4} maxLength={12000} className={fieldClass} value={prompt} onChange={(e) => setPrompt(e.target.value)} placeholder="Leave empty to start from the agent’s existing instructions" /></Field>
      <div className="grid gap-3 md:grid-cols-2">
        <Field label="Name"><input maxLength={160} className={fieldClass} value={name} onChange={(e) => setName(e.target.value)} placeholder={`${agent || "Agent"}, ${scorer ?? "reward model"}`} /></Field>
        <Field label="Workload" hint="Use this identifier when connecting the agent. Defaults to “default”."><input maxLength={2000} className={fieldClass} value={scope} onChange={(e) => setScope(e.target.value)} placeholder="default" /></Field>
        <Field label="Runs per prompt"><input required type="number" min={5} max={500} className={fieldClass} value={runs} onChange={(e) => setRuns(Number(e.target.value))} /></Field>
        <Field label="Maximum rounds"><input required type="number" min={1} max={100} className={fieldClass} value={rounds} onChange={(e) => setRounds(Number(e.target.value))} /></Field>
      </div>
    </div></details>
    <p className="m-0 text-xs leading-relaxed text-muted-foreground">{chosenEval ? `The “${chosenEval.name}” eval (its saved version, pinned) scores each run by how likely it decides “${target}”, across` : model ? `${model.name} scores` : "The selected reward model scores"} {runs} baseline and {runs} candidate runs per round. Better prompts become current after the comparison establishes an improvement. Starting enables up to {rounds} rounds of candidate generation and remote scoring on connected future runs.</p>
    {error && <p role="alert" className="text-sm text-red-600">{error}</p>}
  </form>;
}
