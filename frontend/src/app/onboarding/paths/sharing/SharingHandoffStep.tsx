"use client";

import { useState } from "react";

import { apiFetch } from "@/lib/api";

type AgentChoice = "claude-code" | "cursor" | "codex" | "other";

// Step signature is wider than what we need; this step's UI is path-state-
// independent so we ignore the StepCtx the wizard hands us.
export default function SharingHandoffStep() {
  return (
    <div className="space-y-6">
      <div className="space-y-2">
        <h1 className="font-display text-[28px] leading-[1.1] font-bold tracking-tight text-foreground">
          Keep going from your agent
        </h1>
        <p className="text-sm text-dim max-w-md">
          Two ways to give your existing coding agent the keys to publish
          for you.
        </p>
      </div>

      <CliCard />
      <AgentAuthCard />
    </div>
  );
}

function CliCard() {
  return (
    <div className="rounded-2xl border border-border bg-surface p-5 space-y-2">
      <div className="text-[13px] font-semibold text-foreground">
        Install the CLI
      </div>
      <p className="text-[12px] text-muted leading-relaxed">
        The full integration. Push transcripts automatically, run{" "}
        <code className="text-foreground">stash share</code> from any
        terminal.
      </p>
      <pre className="rounded-md border border-border-subtle bg-background/40 px-3 py-2 text-[12px] font-mono text-foreground overflow-x-auto">
        npm i -g @joinstash/cli
      </pre>
    </div>
  );
}

function AgentAuthCard() {
  const [agent, setAgent] = useState<AgentChoice>("claude-code");
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [approved, setApproved] = useState(false);
  const [creating, setCreating] = useState(false);
  const [approving, setApproving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const deviceName = agent === "other" ? "agent" : agent;

  async function createSession() {
    setCreating(true);
    setError(null);
    try {
      const res = await apiFetch<{ session_id: string }>(
        "/api/v1/users/cli-auth/sessions",
        {
          method: "POST",
          body: JSON.stringify({ device_name: deviceName }),
        },
      );
      setSessionId(res.session_id);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setCreating(false);
    }
  }

  async function approveSession() {
    if (!sessionId) return;
    setApproving(true);
    setError(null);
    try {
      await apiFetch(`/api/v1/users/cli-auth/sessions/${sessionId}/approve`, {
        method: "POST",
      });
      setApproved(true);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setApproving(false);
    }
  }

  return (
    <div className="rounded-2xl border border-border bg-surface p-5 space-y-3">
      <div>
        <div className="text-[13px] font-semibold text-foreground">
          Authorize a coding agent
        </div>
        <p className="text-[12px] text-muted leading-relaxed">
          Mint a named API key for your agent. The CLI will pick it up on
          first run instead of asking you to log in again.
        </p>
      </div>

      <div className="flex flex-wrap gap-2">
        {(["claude-code", "cursor", "codex", "other"] as AgentChoice[]).map(
          (a) => (
            <button
              key={a}
              type="button"
              onClick={() => setAgent(a)}
              className={`rounded-full border px-3 py-1 text-[11.5px] transition-colors ${
                agent === a
                  ? "border-brand bg-brand/10 text-foreground"
                  : "border-border-subtle bg-background/40 text-muted hover:text-foreground"
              }`}
            >
              {a === "claude-code"
                ? "Claude Code"
                : a === "cursor"
                  ? "Cursor"
                  : a === "codex"
                    ? "Codex"
                    : "Other"}
            </button>
          ),
        )}
      </div>

      {!sessionId && (
        <button
          type="button"
          onClick={createSession}
          disabled={creating}
          className="rounded-md bg-brand px-4 py-2 text-[13px] font-medium text-white hover:bg-brand-hover disabled:opacity-60"
        >
          {creating ? "Creating session…" : "Create auth session"}
        </button>
      )}

      {sessionId && !approved && (
        <div className="space-y-3">
          <div className="rounded-md border border-border-subtle bg-background/40 p-3 space-y-1.5">
            <div className="text-[10px] font-mono uppercase tracking-wider text-muted">
              Session ID
            </div>
            <code className="block break-all text-[12px] font-mono text-foreground">
              {sessionId}
            </code>
          </div>
          <p className="text-[12px] text-muted leading-relaxed">
            Click below to approve this session with a fresh key for{" "}
            <strong className="text-foreground">{deviceName}</strong>. The
            CLI will redeem it on first run.
          </p>
          <button
            type="button"
            onClick={approveSession}
            disabled={approving}
            className="rounded-md bg-brand px-4 py-2 text-[13px] font-medium text-white hover:bg-brand-hover disabled:opacity-60"
          >
            {approving ? "Approving…" : "Approve session"}
          </button>
        </div>
      )}

      {approved && (
        <div className="rounded-md border border-brand bg-brand/10 px-3 py-2 text-[12px] text-foreground">
          Approved. The next time {deviceName} runs the CLI, it&rsquo;ll pick
          this up automatically.
        </div>
      )}

      {error && (
        <div className="text-[12px] text-error rounded-lg border border-error/30 bg-error/10 px-3 py-2">
          {error}
        </div>
      )}
    </div>
  );
}
