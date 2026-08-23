"use client";

import { useCallback, useEffect, useState } from "react";

import {
  connectAgentKey,
  connectLocalEndpoint,
  disconnectAgentCredential,
  finishAgentOAuth,
  listAgentCredentials,
  startAgentOAuth,
} from "@/lib/api";

// The provider a user connects for their cloud agent. Claude and Codex support
// OAuth (sign in with your subscription) or an API key; OpenRouter is key-only;
// the local model is an endpoint (base URL + model, key optional, plus optional
// context window / max output tokens — unset → the documented 131072 / 8192).
type Provider = {
  id: string;
  label: string;
  blurb: string;
  oauth: boolean;
  endpoint: boolean;
  keyHint: string;
};

const PROVIDERS: Provider[] = [
  {
    id: "anthropic",
    label: "Claude Code",
    blurb: "Sign in with your Claude subscription, or paste an Anthropic API key.",
    oauth: true,
    endpoint: false,
    keyHint: "sk-ant-…",
  },
  {
    id: "openai",
    label: "Codex",
    blurb: "Sign in with ChatGPT, or paste an OpenAI API key.",
    oauth: true,
    endpoint: false,
    keyHint: "sk-…",
  },
  {
    id: "openrouter",
    label: "OpenRouter",
    blurb: "Run any model on your own OpenRouter key.",
    oauth: false,
    endpoint: false,
    keyHint: "sk-or-…",
  },
  {
    id: "local",
    label: "Local model",
    blurb:
      "Ollama or any OpenAI-compatible endpoint your cloud computer can reach — expose it with a tunnel (cloudflared, ngrok) or self-host it.",
    oauth: false,
    endpoint: true,
    keyHint: "optional key…",
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
          Connect Claude, Codex, OpenRouter, or a local model to run the agent on your own
          account. Pro members without a connection use the managed agent (OpenRouter
          GLM&nbsp;5.2).
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

// Parses an optional size field: "" is unset (null → the documented default
// applies); a filled field must be a positive integer, else NaN — which
// disables Connect instead of silently dropping the user's input.
function parseSizeField(value: string): number | null {
  if (value.trim() === "") return null;
  const n = Number(value);
  return Number.isInteger(n) && n > 0 ? n : NaN;
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
  const [mode, setMode] = useState<"idle" | "key" | "endpoint" | "oauth">("idle");
  const [apiKey, setApiKey] = useState("");
  const [baseUrl, setBaseUrl] = useState("");
  const [modelId, setModelId] = useState("");
  const [localKey, setLocalKey] = useState("");
  const [contextWindow, setContextWindow] = useState("");
  const [maxTokens, setMaxTokens] = useState("");
  const contextWindowValue = parseSizeField(contextWindow);
  const maxTokensValue = parseSizeField(maxTokens);
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

  async function saveEndpoint() {
    setBusy(true);
    setError(null);
    try {
      onChange(
        await connectLocalEndpoint(
          baseUrl.trim(),
          modelId.trim(),
          localKey.trim() || null,
          contextWindowValue,
          maxTokensValue,
        ),
      );
      setMode("idle");
      setBaseUrl("");
      setModelId("");
      setLocalKey("");
      setContextWindow("");
      setMaxTokens("");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not connect endpoint");
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
              onClick={() =>
                setMode(
                  mode === (provider.endpoint ? "endpoint" : "key") ? "idle" : provider.endpoint ? "endpoint" : "key",
                )
              }
              className="rounded-md border border-border px-3 py-1.5 text-[12.5px] text-foreground hover:bg-raised"
            >
              {provider.endpoint ? "Connect endpoint" : "API key"}
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

      {mode === "endpoint" && !connected && provider.endpoint && (
        <div className="mt-3 space-y-2">
          <p className="text-[12.5px] text-muted-foreground">
            The base URL must be reachable from your cloud computer (a tunnel or a
            self-hosted server), and the model id is the one that endpoint serves.
            Optional: the context window and max output tokens written into the
            model entry pi reads. Leave blank for the documented defaults (131072 /
            8192); max output must be below the context window.
          </p>
          <div className="flex flex-col gap-2 sm:flex-row">
            <input
              type="url"
              value={baseUrl}
              onChange={(e) => setBaseUrl(e.target.value)}
              placeholder="http://your-host:11434/v1"
              className="flex-1 rounded-md border border-border bg-surface px-2.5 py-1.5 font-mono text-[12.5px] text-foreground"
            />
            <input
              value={modelId}
              onChange={(e) => setModelId(e.target.value)}
              placeholder="llama3.1:8b"
              className="flex-1 rounded-md border border-border bg-surface px-2.5 py-1.5 font-mono text-[12.5px] text-foreground"
            />
          </div>
          <div className="flex flex-col gap-2 sm:flex-row">
            <input
              type="number"
              min={1}
              aria-label="Context window"
              value={contextWindow}
              onChange={(e) => setContextWindow(e.target.value)}
              placeholder="131072"
              className="flex-1 rounded-md border border-border bg-surface px-2.5 py-1.5 font-mono text-[12.5px] text-foreground"
            />
            <input
              type="number"
              min={1}
              aria-label="Max output tokens"
              value={maxTokens}
              onChange={(e) => setMaxTokens(e.target.value)}
              placeholder="8192"
              className="flex-1 rounded-md border border-border bg-surface px-2.5 py-1.5 font-mono text-[12.5px] text-foreground"
            />
          </div>
          <div className="flex gap-2">
            <input
              type="password"
              value={localKey}
              onChange={(e) => setLocalKey(e.target.value)}
              placeholder={provider.keyHint}
              className="flex-1 rounded-md border border-border bg-surface px-2.5 py-1.5 font-mono text-[12.5px] text-foreground"
            />
            <button
              type="button"
              onClick={saveEndpoint}
              disabled={
                busy ||
                !baseUrl.trim() ||
                !modelId.trim() ||
                Number.isNaN(contextWindowValue) ||
                Number.isNaN(maxTokensValue)
              }
              className="rounded-md bg-brand px-3 py-1.5 text-[12.5px] font-medium text-white disabled:opacity-60"
            >
              Connect
            </button>
          </div>
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
