"use client";

import { useCallback, useEffect, useState } from "react";

import { SectionHeading } from "@/components/developer/DocsPrimitives";
import {
  connectWorkspaceLocalEndpoint,
  disconnectWorkspaceLocalEndpoint,
  listWorkspaceAgentCredentials,
} from "@/lib/api";

// The local endpoint the workspace's agents run on. The credential lives on the
// workspace's scope account (not the operator's personal one), so the nightly
// wiki curator and every other workspace agent resolve to it on their own.
export default function LocalModelSection() {
  const [connected, setConnected] = useState<string[]>([]);
  const [loading, setLoading] = useState(true);
  const [mode, setMode] = useState<"idle" | "endpoint">("idle");
  const [baseUrl, setBaseUrl] = useState("");
  const [modelId, setModelId] = useState("");
  const [localKey, setLocalKey] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const isConnected = connected.includes("local");

  const refresh = useCallback(() => {
    listWorkspaceAgentCredentials()
      .then(setConnected)
      .catch(() => {})
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => refresh(), [refresh]);

  async function connect() {
    setBusy(true);
    setError(null);
    try {
      setConnected(
        await connectWorkspaceLocalEndpoint(baseUrl.trim(), modelId.trim(), localKey.trim() || null),
      );
      setMode("idle");
      setBaseUrl("");
      setModelId("");
      setLocalKey("");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not connect endpoint");
    } finally {
      setBusy(false);
    }
  }

  async function disconnect() {
    setBusy(true);
    setError(null);
    try {
      setConnected(await disconnectWorkspaceLocalEndpoint());
      setMode("idle");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not disconnect endpoint");
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="mb-12">
      <SectionHeading>Local model</SectionHeading>
      <p className="mt-2 text-[13.5px] leading-6 text-muted-foreground">
        The OpenAI-compatible endpoint (Ollama or similar) the workspace&apos;s agents run on —
        the nightly wiki curator above all. It must be reachable from your cloud computer:
        expose it with a tunnel (cloudflared, ngrok) or self-host it.
      </p>

      {loading ? (
        <p className="mt-4 text-[13.5px] text-muted-foreground">Loading…</p>
      ) : (
        <div className="mt-4 rounded border border-border bg-surface p-5">
          <div className="flex items-center justify-between gap-3">
            <div className="flex items-center gap-2">
              <span className="text-[14px] font-medium text-foreground">Endpoint</span>
              {isConnected && (
                <span className="rounded-sm bg-brand-500/10 px-2 py-0.5 text-[11px] font-medium text-brand-600">
                  Connected
                </span>
              )}
            </div>
            {isConnected ? (
              <button
                type="button"
                onClick={() => void disconnect()}
                disabled={busy}
                className="rounded-sm border border-border px-3 py-1.5 text-[13px] text-dim transition-colors hover:bg-raised hover:text-error disabled:opacity-50"
              >
                Disconnect
              </button>
            ) : (
              <button
                type="button"
                onClick={() => setMode(mode === "endpoint" ? "idle" : "endpoint")}
                disabled={busy}
                className="rounded-sm border border-border px-3 py-1.5 text-[13px] text-foreground transition-colors hover:bg-raised disabled:opacity-50"
              >
                Connect endpoint
              </button>
            )}
          </div>

          {mode === "endpoint" && !isConnected && (
            <div className="mt-4 space-y-2">
              <p className="text-[12.5px] text-muted-foreground">
                The base URL must be reachable from your cloud computer (a tunnel or a
                self-hosted server), and the model id is the one that endpoint serves.
              </p>
              <input
                type="url"
                value={baseUrl}
                onChange={(e) => setBaseUrl(e.target.value)}
                placeholder="http://your-host:11434/v1"
                className="w-full rounded border border-border bg-base px-3 py-2 font-mono text-[13px] text-foreground placeholder:text-muted-foreground focus:border-brand-500 focus:outline-none"
              />
              <input
                value={modelId}
                onChange={(e) => setModelId(e.target.value)}
                placeholder="llama3.1:8b"
                className="w-full rounded border border-border bg-base px-3 py-2 font-mono text-[13px] text-foreground placeholder:text-muted-foreground focus:border-brand-500 focus:outline-none"
              />
              <div className="flex flex-col gap-2 sm:flex-row">
                <input
                  type="password"
                  value={localKey}
                  onChange={(e) => setLocalKey(e.target.value)}
                  placeholder="optional key…"
                  className="flex-1 rounded border border-border bg-base px-3 py-2 font-mono text-[13px] text-foreground placeholder:text-muted-foreground focus:border-brand-500 focus:outline-none"
                />
                <button
                  type="button"
                  onClick={() => void connect()}
                  disabled={busy || !baseUrl.trim() || !modelId.trim()}
                  className="rounded-sm bg-brand-500 px-3 py-2 text-[13px] font-medium text-white transition-colors hover:bg-brand-600 disabled:opacity-50"
                >
                  Connect
                </button>
              </div>
            </div>
          )}

          {error && <p className="mt-3 text-[12.5px] text-error">{error}</p>}
        </div>
      )}
    </section>
  );
}
