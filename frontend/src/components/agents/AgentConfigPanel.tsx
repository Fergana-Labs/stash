"use client";

import { useEffect, useState } from "react";

import { type Agent, deleteAgent, listAgents, updateAgent } from "@/lib/api";

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

  useEffect(() => {
    listAgents()
      .then((all) => setAgent(all.find((a) => a.id === agentId) ?? null))
      .catch(() => setAgent(null));
  }, [agentId]);

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

  return (
    <div className="mx-auto w-full max-w-2xl space-y-5 px-6 py-6">
      <div className="flex items-center justify-between">
        <h1 className="text-[18px] font-semibold text-foreground">Agent settings</h1>
        {!agent.is_default && !agent.is_curator && (
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
