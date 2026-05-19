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
    <div
      style={{
        border: "1px solid var(--border, #e5e7eb)",
        borderRadius: 8,
        padding: 16,
        display: "flex",
        alignItems: "center",
        justifyContent: "space-between",
        gap: 16,
      }}
    >
      <div style={{ minWidth: 0, flex: 1 }}>
        <div style={{ fontWeight: 600, fontSize: 15 }}>{status.display_name}</div>
        {status.connected ? (
          <div style={{ fontSize: 13, color: "var(--muted, #6b7280)", marginTop: 4 }}>
            Connected as{" "}
            <strong>{status.account_display_name || status.account_email || "—"}</strong>
            {status.account_email && status.account_display_name ? (
              <span> ({status.account_email})</span>
            ) : null}
          </div>
        ) : (
          <div style={{ fontSize: 13, color: "var(--muted, #6b7280)", marginTop: 4 }}>
            Not connected · scopes: {status.scopes.join(", ") || "(none)"}
          </div>
        )}
      </div>
      <div>
        {status.connected ? (
          <button
            type="button"
            onClick={onDisconnect}
            disabled={busy}
            style={{
              padding: "6px 12px",
              border: "1px solid var(--border, #e5e7eb)",
              borderRadius: 6,
              background: "transparent",
              cursor: busy ? "wait" : "pointer",
            }}
          >
            Disconnect
          </button>
        ) : (
          <button
            type="button"
            onClick={onConnect}
            disabled={busy}
            style={{
              padding: "6px 12px",
              borderRadius: 6,
              border: "1px solid var(--border, #2563eb)",
              background: "var(--accent, #2563eb)",
              color: "white",
              cursor: busy ? "wait" : "pointer",
            }}
          >
            Connect
          </button>
        )}
      </div>
    </div>
  );
}
