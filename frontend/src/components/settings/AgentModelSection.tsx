"use client";

import { useCallback, useEffect, useState } from "react";

import {
  connectAgentKey,
  disconnectAgentCredential,
  finishAgentOAuth,
  listAgentCredentials,
  startAgentOAuth,
} from "@/lib/api";

// The provider a user connects for their cloud agent. Claude and Codex support
// OAuth (sign in with your subscription) or an API key; OpenRouter is key-only.
type Provider = {
  id: string;
  label: string;
  blurb: string;
  oauth: boolean;
  keyHint: string;
};

const PROVIDERS: Provider[] = [
  {
    id: "anthropic",
    label: "Claude Code",
    blurb: "Sign in with your Claude subscription, or paste an Anthropic API key.",
    oauth: true,
    keyHint: "sk-ant-…",
  },
  {
    id: "openai",
    label: "Codex",
    blurb: "Sign in with ChatGPT, or paste an OpenAI API key.",
    oauth: true,
    keyHint: "sk-…",
  },
  {
    id: "openrouter",
    label: "OpenRouter",
    blurb: "Run any model on your own OpenRouter key.",
    oauth: false,
    keyHint: "sk-or-…",
  },
];

export default function AgentModelSection() {
  const [connected, setConnected] = useState<string[]>([]);
  const [loading, setLoading] = useState(true);

  const refresh = useCallback(() => {
    listAgentCredentials()
      .then(setConnected)
      .catch(() => {})
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => refresh(), [refresh]);

  return (
    <section className="rounded-2xl border border-border bg-surface p-6 space-y-4">
      <div>
        <h2 className="text-lg font-semibold text-foreground">Cloud agent model</h2>
        <p className="text-sm text-muted-foreground mt-1">
          Connect Claude, Codex, or OpenRouter to run the agent on your own account. Pro
          members without a connection use the managed agent (OpenRouter GLM&nbsp;5.2).
        </p>
      </div>
      {loading ? (
        <div className="text-sm text-muted-foreground">Loading…</div>
      ) : (
        <div className="space-y-3">
          {PROVIDERS.map((p) => (
            <ProviderRow
              key={p.id}
              provider={p}
              connected={connected.includes(p.id)}
              onChange={setConnected}
            />
          ))}
        </div>
      )}
    </section>
  );
}

function ProviderRow({
  provider,
  connected,
  onChange,
}: {
  provider: Provider;
  connected: boolean;
  onChange: (c: string[]) => void;
}) {
  const [mode, setMode] = useState<"idle" | "key" | "oauth">("idle");
  const [apiKey, setApiKey] = useState("");
  const [oauthState, setOauthState] = useState<string | null>(null);
  const [pasted, setPasted] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function disconnect() {
    setBusy(true);
    try {
      onChange(await disconnectAgentCredential(provider.id));
    } finally {
      setBusy(false);
    }
  }

  async function saveKey() {
    setBusy(true);
    setError(null);
    try {
      onChange(await connectAgentKey(provider.id, apiKey));
      setMode("idle");
      setApiKey("");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not save key");
    } finally {
      setBusy(false);
    }
  }

  async function beginOAuth() {
    setBusy(true);
    setError(null);
    try {
      const { authorize_url, state } = await startAgentOAuth(provider.id);
      setOauthState(state);
      setMode("oauth");
      window.open(authorize_url, "_blank", "noopener,noreferrer");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not start sign-in");
    } finally {
      setBusy(false);
    }
  }

  async function finishOAuth() {
    if (!oauthState) return;
    setBusy(true);
    setError(null);
    try {
      onChange(await finishAgentOAuth(provider.id, pasted, oauthState));
      setMode("idle");
      setPasted("");
      setOauthState(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not complete sign-in");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="rounded-xl border border-border bg-base p-4">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="flex items-center gap-2">
            <span className="text-[14px] font-medium text-foreground">{provider.label}</span>
            {connected && (
              <span className="rounded-full bg-[var(--color-success)]/15 px-2 py-0.5 text-[11px] font-medium text-[var(--color-success)]">
                Connected
              </span>
            )}
          </div>
          <p className="mt-0.5 text-[12.5px] text-muted-foreground">{provider.blurb}</p>
        </div>
        {connected ? (
          <button
            type="button"
            onClick={disconnect}
            disabled={busy}
            className="shrink-0 rounded-md border border-border px-3 py-1.5 text-[12.5px] text-dim hover:text-error"
          >
            Disconnect
          </button>
        ) : (
          <div className="flex shrink-0 gap-2">
            {provider.oauth && (
              <button
                type="button"
                onClick={beginOAuth}
                disabled={busy}
                className="rounded-md bg-brand px-3 py-1.5 text-[12.5px] font-medium text-white hover:bg-brand-hover disabled:opacity-60"
              >
                Sign in
              </button>
            )}
            <button
              type="button"
              onClick={() => setMode(mode === "key" ? "idle" : "key")}
              className="rounded-md border border-border px-3 py-1.5 text-[12.5px] text-foreground hover:bg-raised"
            >
              API key
            </button>
          </div>
        )}
      </div>

      {mode === "key" && !connected && (
        <div className="mt-3 flex gap-2">
          <input
            type="password"
            value={apiKey}
            onChange={(e) => setApiKey(e.target.value)}
            placeholder={provider.keyHint}
            className="flex-1 rounded-md border border-border bg-surface px-2.5 py-1.5 font-mono text-[12.5px] text-foreground"
          />
          <button
            type="button"
            onClick={saveKey}
            disabled={busy || !apiKey.trim()}
            className="rounded-md bg-brand px-3 py-1.5 text-[12.5px] font-medium text-white disabled:opacity-60"
          >
            Save
          </button>
        </div>
      )}

      {mode === "oauth" && !connected && (
        <div className="mt-3 space-y-2">
          <p className="text-[12.5px] text-muted-foreground">
            Approve in the tab that opened, then paste the code it shows you here.
          </p>
          <div className="flex gap-2">
            <input
              value={pasted}
              onChange={(e) => setPasted(e.target.value)}
              placeholder="Paste the code"
              className="flex-1 rounded-md border border-border bg-surface px-2.5 py-1.5 font-mono text-[12.5px] text-foreground"
            />
            <button
              type="button"
              onClick={finishOAuth}
              disabled={busy || !pasted.trim()}
              className="rounded-md bg-brand px-3 py-1.5 text-[12.5px] font-medium text-white disabled:opacity-60"
            >
              Connect
            </button>
          </div>
        </div>
      )}

      {error && <p className="mt-2 text-[12px] text-error">{error}</p>}
    </div>
  );
}
