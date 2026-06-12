"use client";

import { useCallback, useEffect, useState } from "react";

import { connectMcpPreset, disconnectMcpServer, listMcpPresets, type McpPreset } from "@/lib/mcp";

import { RenderIcon } from "./BrandIcons";
import { CredentialForm, primaryButton, secondaryButton } from "./pickers";

const PRESET_ICONS: Record<string, React.ReactNode> = {
  render: <RenderIcon />,
};

// Connect surface for agent tool providers (MCP). Pasting an API key stores
// it encrypted server-side and exposes the provider's curated read-only
// tools to the workspace's agents through the Stash MCP proxy.
export default function McpConnectorList({ workspaceId }: { workspaceId: string }) {
  const [presets, setPresets] = useState<McpPreset[]>([]);
  const [expanded, setExpanded] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    const { presets } = await listMcpPresets(workspaceId);
    setPresets(presets);
  }, [workspaceId]);

  useEffect(() => {
    refresh().catch((e) => {
      setError(e instanceof Error ? e.message : "Could not load agent tools");
    });
  }, [refresh]);

  async function connect(preset: McpPreset, values: Record<string, string>) {
    setBusy(preset.name);
    setError(null);
    try {
      await connectMcpPreset(workspaceId, preset.name, values.api_key);
      setExpanded(null);
      await refresh();
      return true;
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not connect");
      return false;
    } finally {
      setBusy(null);
    }
  }

  async function disconnect(preset: McpPreset) {
    setBusy(preset.name);
    setError(null);
    try {
      await disconnectMcpServer(workspaceId, preset.name);
      await refresh();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not disconnect");
    } finally {
      setBusy(null);
    }
  }

  return (
    <div className="space-y-2">
      {presets.map((preset) => (
        <div key={preset.name} className="rounded-lg border border-border bg-surface px-3 py-2.5">
          <div className="flex items-center gap-3">
            <span className="flex h-5 w-5 shrink-0 items-center justify-center">
              {PRESET_ICONS[preset.name]}
            </span>
            <div className="min-w-0 flex-1">
              <div className="text-[13.5px] font-medium text-foreground">{preset.label}</div>
              <div className="truncate text-[11.5px] text-muted">
                {preset.connected
                  ? `Connected — agents get ${preset.tool_allowlist.length} read-only tools`
                  : "Give your agents read-only access via MCP."}
              </div>
            </div>
            <div className="flex shrink-0 items-center gap-2">
              {preset.connected ? (
                <button
                  type="button"
                  onClick={() => void disconnect(preset)}
                  disabled={busy === preset.name}
                  className={secondaryButton()}
                >
                  Disconnect
                </button>
              ) : (
                <button
                  type="button"
                  onClick={() =>
                    setExpanded((value) => (value === preset.name ? null : preset.name))
                  }
                  disabled={busy === preset.name}
                  className={primaryButton()}
                >
                  {expanded === preset.name ? "Cancel" : "Connect"}
                </button>
              )}
            </div>
          </div>

          {expanded === preset.name && !preset.connected && (
            <CredentialForm
              fields={[
                {
                  name: "api_key",
                  label: `${preset.label} API key`,
                  secret: true,
                  placeholder: "rnd_…",
                  help: preset.key_help,
                },
              ]}
              busy={busy === preset.name}
              onSubmit={(values) => connect(preset, values)}
            />
          )}
        </div>
      ))}

      {error && (
        <div className="rounded-md border border-error/30 bg-error/10 px-3 py-2 text-[12px] text-error">
          {error}
        </div>
      )}
    </div>
  );
}
