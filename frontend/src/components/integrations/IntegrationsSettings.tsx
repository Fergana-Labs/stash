"use client";

import { useCallback, useEffect, useState } from "react";

import { IntegrationStatus, listIntegrations } from "@/lib/integrations";

import IntegrationCard from "./IntegrationCard";

/**
 * Generic Integrations settings panel. Iterates every provider returned
 * by `/api/v1/integrations` — adding a new provider on the backend
 * automatically shows up here. No frontend changes needed per provider.
 */
export default function IntegrationsSettings() {
  const [providers, setProviders] = useState<IntegrationStatus[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    try {
      const r = await listIntegrations();
      setProviders(r.providers);
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  return (
    <div style={{ maxWidth: 720, padding: "24px 16px" }}>
      <h1 style={{ fontSize: 22, fontWeight: 700, marginBottom: 8 }}>Integrations</h1>
      <p style={{ color: "var(--muted, #6b7280)", marginBottom: 20, fontSize: 14 }}>
        Connect third-party accounts so Stash can import content and export your
        decks. Disconnect at any time — revoking here also revokes the token on
        the provider.
      </p>

      {error && (
        <div
          style={{
            background: "rgba(220, 38, 38, 0.08)",
            border: "1px solid rgba(220, 38, 38, 0.3)",
            color: "rgb(185, 28, 28)",
            padding: 12,
            borderRadius: 8,
            marginBottom: 16,
            fontSize: 13,
          }}
        >
          {error}
        </div>
      )}

      {providers === null ? (
        <div style={{ color: "var(--muted, #6b7280)" }}>Loading…</div>
      ) : providers.length === 0 ? (
        <div style={{ color: "var(--muted, #6b7280)" }}>No integrations registered.</div>
      ) : (
        <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
          {providers.map((p) => (
            <IntegrationCard key={p.provider} status={p} onChanged={refresh} />
          ))}
        </div>
      )}
    </div>
  );
}
