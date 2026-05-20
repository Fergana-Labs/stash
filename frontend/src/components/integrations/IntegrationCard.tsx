"use client";

import { useState } from "react";

import {
  IntegrationProvider,
  IntegrationStatus,
  disconnectIntegration,
  startConnect,
} from "@/lib/integrations";

type Props = {
  status: IntegrationStatus;
  onChanged?: () => void;
};

/**
 * Generic card for any registered integration. Renders the provider's
 * display_name, scopes, and a Connect/Disconnect action. Provider-specific
 * features (picker buttons, etc.) compose this for the auth state but
 * own their own resource UI.
 */
export default function IntegrationCard({ status, onChanged }: Props) {
  const [busy, setBusy] = useState(false);

  async function onConnect() {
    setBusy(true);
    try {
      await startConnect(status.provider as IntegrationProvider);
    } catch (e) {
      setBusy(false);
      alert(e instanceof Error ? e.message : String(e));
    }
    // On success we've navigated away; nothing more to do.
  }

  async function onDisconnect() {
    if (!confirm(`Disconnect ${status.display_name}?`)) return;
    setBusy(true);
    try {
      await disconnectIntegration(status.provider as IntegrationProvider);
      onChanged?.();
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="rounded-xl border border-border bg-background p-4 flex items-center gap-4">
      <div className="min-w-0 flex-1">
        <div className="text-sm font-semibold text-foreground">{status.display_name}</div>
        {status.connected ? (
          <div className="text-xs text-muted mt-0.5">
            Connected as{" "}
            <span className="font-medium text-foreground">
              {status.account_display_name || status.account_email || "—"}
            </span>
            {status.account_email && status.account_display_name ? (
              <span className="text-muted"> ({status.account_email})</span>
            ) : null}
          </div>
        ) : (
          <div className="text-xs text-muted mt-0.5">
            Not connected
            {status.scopes.length > 0 ? (
              <>
                {" "}
                · scopes:{" "}
                <span className="font-mono">{status.scopes.join(", ")}</span>
              </>
            ) : null}
          </div>
        )}
      </div>
      {status.connected ? (
        <button
          type="button"
          onClick={onDisconnect}
          disabled={busy}
          className="text-xs font-medium px-3 py-1.5 rounded-md border border-border hover:bg-raised disabled:opacity-50 transition-colors"
        >
          {busy ? "…" : "Disconnect"}
        </button>
      ) : (
        <button
          type="button"
          onClick={onConnect}
          disabled={busy}
          className="text-xs font-semibold px-3 py-1.5 rounded-md bg-brand hover:bg-brand-hover text-white disabled:opacity-60 transition-colors"
        >
          {busy ? "…" : "Connect"}
        </button>
      )}
    </div>
  );
}
