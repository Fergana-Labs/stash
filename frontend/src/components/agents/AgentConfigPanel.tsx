"use client";

import { useEffect, useRef, useState } from "react";

import { type Citation, streamAgentRun } from "@/lib/agentChat";
import {
  type Agent,
  type AgentPrompt,
  deleteAgent,
  getAgentPrompt,
  listAgents,
  updateAgent,
} from "@/lib/api";

const MODELS = [
  { value: "", label: "Auto (your connected model)" },
  { value: "anthropic", label: "Claude Code" },
  { value: "openai", label: "Codex" },
  { value: "openrouter", label: "OpenRouter (GLM 5.2 managed)" },
];

// Config for one agent: model, persona, run mode + schedule, channel binding.
export default function AgentConfigPanel({
  agentId,
  onChanged,
}: {
  agentId: string;
  onChanged?: () => void;
}) {
  const [agent, setAgent] = useState<Agent | null>(null);
  const [saving, setSaving] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);
  const [run, setRun] = useState<RunState | null>(null);
  const [prompt, setPrompt] = useState<AgentPrompt | null>(null);
  const abortRef = useRef<AbortController | null>(null);

  useEffect(() => {
    listAgents()
      .then((all) => setAgent(all.find((a) => a.id === agentId) ?? null))
      .catch(() => setAgent(null));
  }, [agentId]);

  // The curator's prompt is server-built, not a user field — fetch it to show
  // read-only so you can see exactly what it runs.
  useEffect(() => {
    if (!agent?.is_curator) return;
    getAgentPrompt(agent.id)
      .then(setPrompt)
      .catch(() => setPrompt(null));
  }, [agent?.is_curator, agent?.id]);

  useEffect(() => () => abortRef.current?.abort(), []);

  if (!agent) return <div className="p-6 text-[13px] text-muted-foreground">Loading agent…</div>;

  function set<K extends keyof Agent>(key: K, value: Agent[K]) {
    setAgent((a) => (a ? { ...a, [key]: value } : a));
  }

  async function save() {
    if (!agent) return;
    setSaving(true);
    setMsg(null);
    try {
      await updateAgent(agent.id, {
        name: agent.name,
        model_provider: agent.model_provider || null,
        system_prompt: agent.system_prompt || null,
        run_mode: agent.run_mode,
        schedule_cron: agent.schedule_cron || null,
        schedule_prompt: agent.schedule_prompt || null,
        slack_bound: agent.slack_bound,
        telegram_bound: agent.telegram_bound,
      });
      setMsg("Saved.");
      window.dispatchEvent(new Event("agents-changed"));
      onChanged?.();
    } catch (e) {
      setMsg(e instanceof Error ? e.message : "Could not save");
    } finally {
      setSaving(false);
    }
  }

  async function remove() {
    if (!agent) return;
    await deleteAgent(agent.id);
    window.dispatchEvent(new Event("agents-changed"));
    setMsg("Deleted — you can close this tab.");
    onChanged?.();
  }

  async function runNow() {
    if (!agent || run?.streaming) return;
    const controller = new AbortController();
    abortRef.current = controller;
    setRun({ streaming: true, status: "Starting…", text: "", tools: [], error: null });
    try {
      await streamAgentRun({
        agentId: agent.id,
        signal: controller.signal,
        onStatus: (stage) =>
          setRun((r) => (r ? { ...r, status: stage === "waking" ? "Starting your computer…" : stage } : r)),
        onText: (delta) => setRun((r) => (r ? { ...r, status: null, text: r.text + delta } : r)),
        onTool: (c: Citation) =>
          setRun((r) =>
            r && !r.tools.some((x) => x.id === c.id) ? { ...r, tools: [...r.tools, c] } : r,
          ),
        onError: (message) => setRun((r) => (r ? { ...r, error: message } : r)),
      });
      window.dispatchEvent(new Event("agents-changed"));
    } catch (e) {
      if ((e as Error).name !== "AbortError") {
        setRun((r) => (r ? { ...r, error: e instanceof Error ? e.message : String(e) } : r));
      }
    } finally {
      setRun((r) => (r ? { ...r, streaming: false, status: null } : r));
      abortRef.current = null;
    }
  }

  // The curator is a reserved system agent, not a user-configurable one — it
  // gets a dedicated read-only view (identity, schedule, run-on-demand, prompt)
  // rather than the name/model/persona/channel controls of a normal agent.
  if (agent.is_curator) {
    return (
      <div className="mx-auto w-full max-w-2xl space-y-5 px-6 py-6">
        <div>
          <h1 className="text-[18px] font-semibold text-foreground">Memory curator</h1>
          <p className="mt-1.5 text-[13px] leading-5 text-dim">
            A reserved system agent. Once a day it reads what changed in your stash and
            curates it into an organized wiki in your Memory folder. It isn&apos;t a normal
            agent — there&apos;s no name, model, persona, or channel to set. Run it on demand
            and read exactly what it does below.
          </p>
        </div>

        <Field label="Schedule">
          <div className="text-[13px] text-foreground">Daily · automatic</div>
        </Field>

        <RunOnDemand isCurator run={run} onRun={runNow} />

        <Field
          label="System prompt"
          hint="Appended to the coding agent's own system prompt on every run."
        >
          <ReadOnlyPrompt text={prompt?.system_prompt ?? null} />
        </Field>
        <Field
          label="Curation instruction"
          hint="Built automatically from your Memory folder and the changes since its last run."
        >
          <ReadOnlyPrompt text={prompt?.run_prompt ?? null} />
        </Field>
      </div>
    );
  }

  return (
    <div className="mx-auto w-full max-w-2xl space-y-5 px-6 py-6">
      <div className="flex items-center justify-between">
        <h1 className="text-[18px] font-semibold text-foreground">Agent settings</h1>
        {!agent.is_default && (
          <button
            type="button"
            onClick={remove}
            className="rounded-md border border-border px-3 py-1.5 text-[12.5px] text-dim hover:text-error"
          >
            Delete agent
          </button>
        )}
      </div>

      <Field label="Name">
        <input
          value={agent.name}
          onChange={(e) => set("name", e.target.value)}
          className="w-full rounded-md border border-border bg-base px-3 py-2 text-[13px] text-foreground"
        />
      </Field>

      <Field label="Model" hint="Which harness runs this agent's turns.">
        <select
          value={agent.model_provider ?? ""}
          onChange={(e) => set("model_provider", (e.target.value || null) as Agent["model_provider"])}
          className="w-full rounded-md border border-border bg-base px-3 py-2 text-[13px] text-foreground"
        >
          {MODELS.map((m) => (
            <option key={m.value} value={m.value}>
              {m.label}
            </option>
          ))}
        </select>
      </Field>

      <Field label="Persona" hint="Extra instructions appended to the agent's system prompt.">
        <textarea
          value={agent.system_prompt ?? ""}
          onChange={(e) => set("system_prompt", e.target.value || null)}
          rows={3}
          placeholder="e.g. Answer concisely and cite sources."
          className="w-full resize-none rounded-md border border-border bg-base px-3 py-2 text-[13px] text-foreground"
        />
      </Field>

      <Field label="Run mode">
        <div className="flex gap-4 text-[13px] text-foreground">
          {["chat", "scheduled"].map((mode) => (
            <label key={mode} className="flex items-center gap-1.5">
              <input
                type="radio"
                checked={agent.run_mode === mode}
                onChange={() => set("run_mode", mode)}
              />
              {mode === "chat" ? "Interactive chat" : "Scheduled"}
            </label>
          ))}
        </div>
      </Field>

      {agent.run_mode === "scheduled" && (
        <div className="space-y-3 rounded-lg border border-border bg-surface p-3">
          <Field label="Schedule (cron)" hint="UTC. e.g. 0 9 * * * runs daily at 09:00.">
            <input
              value={agent.schedule_cron ?? ""}
              onChange={(e) => set("schedule_cron", e.target.value || null)}
              placeholder="0 9 * * *"
              className="w-full rounded-md border border-border bg-base px-3 py-2 font-mono text-[12.5px] text-foreground"
            />
          </Field>
          <Field label="Scheduled prompt" hint="What the agent does on each run.">
            <textarea
              value={agent.schedule_prompt ?? ""}
              onChange={(e) => set("schedule_prompt", e.target.value || null)}
              rows={2}
              placeholder="e.g. Summarize what changed in my stash today."
              className="w-full resize-none rounded-md border border-border bg-base px-3 py-2 text-[13px] text-foreground"
            />
          </Field>
        </div>
      )}

      {agent.run_mode === "scheduled" && <RunOnDemand isCurator={false} run={run} onRun={runNow} />}

      <Field label="Channels" hint="Which channels this agent answers.">
        <div className="flex gap-4 text-[13px] text-foreground">
          <label className="flex items-center gap-1.5">
            <input
              type="checkbox"
              checked={agent.slack_bound}
              onChange={(e) => set("slack_bound", e.target.checked)}
            />
            Slack
          </label>
          <label className="flex items-center gap-1.5">
            <input
              type="checkbox"
              checked={agent.telegram_bound}
              onChange={(e) => set("telegram_bound", e.target.checked)}
            />
            Telegram
          </label>
        </div>
      </Field>

      <div className="flex items-center gap-3">
        <button
          type="button"
          onClick={save}
          disabled={saving}
          className="rounded-md bg-brand px-4 py-2 text-[13px] font-medium text-white hover:bg-brand-hover disabled:opacity-60"
        >
          {saving ? "Saving…" : "Save"}
        </button>
        {msg && <span className="text-[12.5px] text-muted-foreground">{msg}</span>}
      </div>
    </div>
  );
}

// Shared "Run now" control + live output for scheduled agents (curator included).
function RunOnDemand({
  isCurator,
  run,
  onRun,
}: {
  isCurator: boolean;
  run: RunState | null;
  onRun: () => void;
}) {
  return (
    <div className="space-y-3 rounded-lg border border-border bg-surface p-3">
      <div className="flex items-center justify-between">
        <div>
          <div className="text-[12.5px] font-medium text-foreground">Run on demand</div>
          <div className="text-[11.5px] text-muted-foreground">
            {isCurator
              ? "Trigger a curation pass now instead of waiting for the daily schedule. Your watermark is untouched, so it's safe to repeat."
              : "Run this scheduled agent now to test it."}
          </div>
        </div>
        <button
          type="button"
          onClick={onRun}
          disabled={run?.streaming}
          className="shrink-0 rounded-md border border-border px-3 py-1.5 text-[12.5px] font-medium text-foreground hover:bg-raised disabled:opacity-60"
        >
          {run?.streaming ? "Running…" : "Run now"}
        </button>
      </div>
      {run && <RunOutput run={run} />}
    </div>
  );
}

// A server-built prompt shown read-only (the curator's, which isn't editable).
function ReadOnlyPrompt({ text }: { text: string | null }) {
  if (text === null) {
    return <div className="text-[12px] text-muted-foreground">Loading…</div>;
  }
  return (
    <pre className="scroll-thin max-h-72 overflow-auto whitespace-pre-wrap break-words rounded-md border border-border bg-base px-3 py-2.5 text-[12px] leading-relaxed text-foreground">
      {text}
    </pre>
  );
}

type RunState = {
  streaming: boolean;
  status: string | null;
  text: string;
  tools: Citation[];
  error: string | null;
};

// Live view of an on-demand run: a status line, the tool calls it made (e.g.
// the curator's stash CLI commands), and its streamed final report.
function RunOutput({ run }: { run: RunState }) {
  return (
    <div className="space-y-2 rounded-md border border-border bg-base p-3">
      {run.status && (
        <div className="flex items-center gap-2 text-[12px] text-dim">
          <span className="inline-block h-2 w-2 animate-pulse rounded-full bg-brand" />
          {run.status}
        </div>
      )}
      {run.tools.length > 0 && (
        <div className="flex flex-wrap gap-1.5">
          {run.tools.map((c) => (
            <span
              key={c.id}
              className="rounded border border-border bg-surface px-1.5 py-0.5 font-mono text-[11px] text-muted-foreground"
            >
              {c.label}
            </span>
          ))}
        </div>
      )}
      {run.text && (
        <pre className="scroll-thin max-h-64 overflow-auto whitespace-pre-wrap break-words text-[12.5px] leading-relaxed text-foreground">
          {run.text}
        </pre>
      )}
      {run.error && (
        <div className="rounded border border-error/30 bg-error/10 px-2.5 py-1.5 text-[12px] text-error">
          {run.error}
        </div>
      )}
      {!run.streaming && !run.error && !run.text && (
        <div className="text-[12px] text-muted-foreground">Run finished with no output.</div>
      )}
    </div>
  );
}

function Field({
  label,
  hint,
  children,
}: {
  label: string;
  hint?: string;
  children: React.ReactNode;
}) {
  return (
    <div className="space-y-1.5">
      <div className="text-[12.5px] font-medium text-foreground">{label}</div>
      {children}
      {hint && <div className="text-[11.5px] text-muted-foreground">{hint}</div>}
    </div>
  );
}
