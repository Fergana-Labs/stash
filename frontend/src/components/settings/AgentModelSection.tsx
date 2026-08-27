"use client";

import { useCallback, useEffect, useState } from "react";

import {
  connectAgentKey,
  connectLocalEndpoint,
  disconnectAgentCredential,
  finishAgentOAuth,
  getLocalModelsJson,
  listAgentCredentials,
  resetLocalModelsJson,
  saveLocalModelsJson,
  startAgentOAuth,
  testLocalEndpoint,
  type AgentCredentials,
  type LocalCredential,
  type LocalEndpointTest,
} from "@/lib/api";

// The provider a user connects for their cloud agent. Claude and Codex support
// OAuth (sign in with your subscription) or an API key; OpenRouter is key-only;
// the local model is an endpoint (base URL + model, key optional).
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

// The user's own key, shown back to them only ever masked: enough of both
// ends to tell two keys apart, never the middle that would work in a request.
export function maskKey(key: string): string {
  return key.length >= 8 ? `${key.slice(0, 4)}…${key.slice(-4)}` : "••••";
}

export default function AgentModelSection() {
  const [creds, setCreds] = useState<AgentCredentials>({ connected: [], local: null });
  // The last local doc seen this session — after a disconnect the form
  // prefills base URL and model from it, so reconnecting is one key entry.
  const [lastLocal, setLastLocal] = useState<LocalCredential | null>(null);
  const [loading, setLoading] = useState(true);

  const refresh = useCallback(() => {
    listAgentCredentials()
      .then((data) => {
        setCreds(data);
        if (data.local) setLastLocal(data.local);
      })
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
              connected={creds.connected.includes(p.id)}
              refresh={refresh}
              localDoc={creds.local ?? lastLocal}
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
  refresh,
  localDoc,
}: {
  provider: Provider;
  connected: boolean;
  refresh: () => void;
  localDoc: LocalCredential | null;
}) {
  const [mode, setMode] = useState<"idle" | "key" | "endpoint" | "oauth">("idle");
  const [apiKey, setApiKey] = useState("");
  const [baseUrl, setBaseUrl] = useState("");
  const [modelId, setModelId] = useState("");
  const [localKey, setLocalKey] = useState("");
  const [oauthState, setOauthState] = useState<string | null>(null);
  const [pasted, setPasted] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [modelsOpen, setModelsOpen] = useState(false);
  const [revealed, setRevealed] = useState(false);
  const [testing, setTesting] = useState(false);
  const [test, setTest] = useState<LocalEndpointTest | null>(null);

  function openForm() {
    const target = provider.endpoint ? "endpoint" : "key";
    if (mode === target) {
      setMode("idle");
      return;
    }
    if (provider.endpoint) {
      // Reconnecting is one key entry, not three fields re-typed — and the
      // key input always starts empty: it is never remembered client-side.
      setBaseUrl(localDoc?.base_url ?? "");
      setModelId(localDoc?.model ?? "");
      setLocalKey("");
      setTest(null);
      setRevealed(false);
    }
    setMode(target);
  }

  async function disconnect() {
    setBusy(true);
    try {
      await disconnectAgentCredential(provider.id);
      setRevealed(false);
      refresh();
    } finally {
      setBusy(false);
    }
  }

  async function saveKey() {
    setBusy(true);
    setError(null);
    try {
      await connectAgentKey(provider.id, apiKey);
      setMode("idle");
      setApiKey("");
      refresh();
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
      await connectLocalEndpoint(baseUrl.trim(), modelId.trim(), localKey.trim() || null);
      setMode("idle");
      setBaseUrl("");
      setModelId("");
      setLocalKey("");
      setTest(null);
      setRevealed(false);
      refresh();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not connect endpoint");
    } finally {
      setBusy(false);
    }
  }

  async function testConnection() {
    setTesting(true);
    setError(null);
    setTest(null);
    try {
      setTest(await testLocalEndpoint(baseUrl.trim(), modelId.trim(), localKey.trim() || null));
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not test the endpoint");
    } finally {
      setTesting(false);
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
      await finishAgentOAuth(provider.id, pasted, oauthState);
      setMode("idle");
      setPasted("");
      setOauthState(null);
      refresh();
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
          {connected && provider.endpoint && localDoc && (
            <div className="mt-1.5 flex flex-wrap items-center gap-2">
              <span className="rounded-full bg-raised px-2 py-0.5 text-[11px] font-medium text-muted-foreground">
                {localDoc.api_key ? "key set" : "no key"}
              </span>
              {localDoc.api_key && (
                <span className="flex items-center gap-1.5">
                  <span
                    className={
                      revealed
                        ? "select-text font-mono text-[12px] text-foreground"
                        : "font-mono text-[12px] text-muted-foreground"
                    }
                  >
                    {revealed ? localDoc.api_key : maskKey(localDoc.api_key)}
                  </span>
                  <button
                    type="button"
                    onClick={() => setRevealed(!revealed)}
                    className="text-[11px] font-medium text-brand hover:underline"
                  >
                    {revealed ? "Hide" : "Show"}
                  </button>
                </span>
              )}
            </div>
          )}
        </div>
        {connected ? (
          <div className="flex shrink-0 gap-2">
            {provider.endpoint && (
              <button
                type="button"
                onClick={() => setModelsOpen(!modelsOpen)}
                disabled={busy}
                className="rounded-md border border-border px-3 py-1.5 text-[12.5px] text-foreground hover:bg-raised disabled:opacity-60"
              >
                Edit models.json
              </button>
            )}
            <button
              type="button"
              onClick={disconnect}
              disabled={busy}
              className="rounded-md border border-border px-3 py-1.5 text-[12.5px] text-dim hover:text-error"
            >
              Disconnect
            </button>
          </div>
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
              onClick={openForm}
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
          </p>
          <div className="flex flex-col gap-2 sm:flex-row">
            <input
              type="url"
              value={baseUrl}
              onChange={(e) => {
                setBaseUrl(e.target.value);
                setTest(null);
              }}
              placeholder="http://your-host:11434/v1"
              className="flex-1 rounded-md border border-border bg-surface px-2.5 py-1.5 font-mono text-[12.5px] text-foreground"
            />
            <input
              value={modelId}
              onChange={(e) => {
                setModelId(e.target.value);
                setTest(null);
              }}
              placeholder="llama3.1:8b"
              className="flex-1 rounded-md border border-border bg-surface px-2.5 py-1.5 font-mono text-[12.5px] text-foreground"
            />
          </div>
          <div className="flex gap-2">
            <input
              type="password"
              value={localKey}
              onChange={(e) => {
                setLocalKey(e.target.value);
                setTest(null);
              }}
              placeholder={provider.keyHint}
              className="flex-1 rounded-md border border-border bg-surface px-2.5 py-1.5 font-mono text-[12.5px] text-foreground"
            />
            <button
              type="button"
              onClick={testConnection}
              disabled={testing || busy || !baseUrl.trim()}
              className="rounded-md border border-border px-3 py-1.5 text-[12.5px] text-foreground hover:bg-raised disabled:opacity-60"
            >
              Test connection
            </button>
            <button
              type="button"
              onClick={saveEndpoint}
              disabled={busy || !baseUrl.trim() || !modelId.trim()}
              className="rounded-md bg-brand px-3 py-1.5 text-[12.5px] font-medium text-white disabled:opacity-60"
            >
              Connect
            </button>
          </div>
          {test &&
            (test.ok ? (
              <div className="space-y-1">
                <p className="text-[12px] text-[var(--color-success)]">
                  HTTP {test.http_status} · {test.models.length} models
                </p>
                {modelId.trim() && !test.models.includes(modelId.trim()) && (
                  <p className="text-[12px] text-[var(--color-warning)]">
                    {`Model '${modelId.trim()}' is not in the endpoint's model list.`}
                  </p>
                )}
              </div>
            ) : (
              <p className="text-[12px] text-error">
                {test.http_status === null
                  ? `Connection failed: ${test.error_detail}`
                  : `HTTP ${test.http_status}: ${test.error_detail}`}
              </p>
            ))}
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

      {connected && provider.endpoint && modelsOpen && <ModelsJsonEditor />}

      {error && <p className="mt-2 text-[12px] text-error">{error}</p>}
    </div>
  );
}

function ModelsJsonEditor() {
  const [text, setText] = useState<string | null>(null);
  const [stored, setStored] = useState<boolean | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function load() {
    setBusy(true);
    setError(null);
    try {
      const { models_json, stored: s } = await getLocalModelsJson();
      setText(models_json);
      setStored(s);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not load models.json");
    } finally {
      setBusy(false);
    }
  }

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function save() {
    if (text === null) return;
    setBusy(true);
    setError(null);
    try {
      // Sent verbatim — the backend is the single validation surface.
      await saveLocalModelsJson(text);
      setStored(true);
    } catch (e) {
      // Keep the user's text; the last-good server value is untouched.
      setError(e instanceof Error ? e.message : "Could not save models.json");
    } finally {
      setBusy(false);
    }
  }

  async function reset() {
    setBusy(true);
    setError(null);
    try {
      await resetLocalModelsJson();
      const { models_json, stored: s } = await getLocalModelsJson();
      setText(models_json);
      setStored(s);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not reset models.json");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="mt-3 space-y-2">
      <div className="flex items-center justify-between">
        <span className="text-[12.5px] font-medium text-foreground">models.json</span>
        <span className="rounded-full bg-[var(--color-success)]/15 px-2 py-0.5 text-[11px] font-medium text-[var(--color-success)]">
          {stored === true ? "Custom" : "Default"}
        </span>
      </div>
      <textarea
        aria-label="models.json"
        value={text ?? ""}
        onChange={(e) => setText(e.target.value)}
        rows={12}
        spellCheck={false}
        className="w-full rounded-md border border-border bg-surface px-2.5 py-1.5 font-mono text-[12px] text-foreground"
      />
      <div className="flex flex-col gap-2 sm:flex-row">
        <button
          type="button"
          onClick={load}
          disabled={busy}
          className="rounded-md border border-border px-3 py-1.5 text-[12.5px] text-foreground hover:bg-raised disabled:opacity-60"
        >
          Load
        </button>
        <button
          type="button"
          onClick={save}
          disabled={busy || !(text ?? "").trim()}
          className="rounded-md bg-brand px-3 py-1.5 text-[12.5px] font-medium text-white disabled:opacity-60"
        >
          Save
        </button>
        <button
          type="button"
          onClick={reset}
          disabled={busy}
          className="rounded-md border border-border px-3 py-1.5 text-[12.5px] text-dim hover:text-error disabled:opacity-60"
        >
          Reset to default
        </button>
      </div>
      {error && <p className="text-[12px] text-error">{error}</p>}
    </div>
  );
}
