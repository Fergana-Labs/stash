"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useState } from "react";

import { ApiError } from "@/lib/api";
import {
  disconnectIntegration,
  listIntegrations,
  startConnect,
  submitCredentials,
  type IntegrationProvider,
  type IntegrationStatus,
} from "@/lib/integrations";

import { useConfirm } from "../ConfirmDialog";
import { ObsidianIcon } from "./BrandIcons";
import { CONNECTORS, connectorIcon, type Connector } from "./connectors";
import { CredentialForm, primaryButton, secondaryButton } from "./pickers";
import ObsidianVaultDropZone from "./ObsidianVaultDropZone";
import PaywallModal from "../PaywallModal";

type Props = {
  workspaceId: string | null;
  returnTo: string;
  includeObsidian?: boolean;
  onSourceCountChange?: (count: number) => void;
  onObsidianUploaded?: () => void;
};

// Connect-only surface. Connecting an account is done here; adding specific
// projects/repos/pages happens on each integration's dedicated page.
export default function SourceConnectorList({
  workspaceId,
  returnTo,
  includeObsidian = true,
  onObsidianUploaded,
}: Props) {
  const [statuses, setStatuses] = useState<Record<string, IntegrationStatus>>({});
  const [expanded, setExpanded] = useState<IntegrationProvider | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [paymentRequired, setPaymentRequired] = useState(false);
  const confirm = useConfirm();

  const refresh = useCallback(async () => {
    setError(null);
    const integrations = await listIntegrations();
    const nextStatuses: Record<string, IntegrationStatus> = {};
    for (const provider of integrations.providers) {
      nextStatuses[provider.provider] = provider;
    }
    setStatuses(nextStatuses);
  }, []);

  useEffect(() => {
    refresh().catch((e) => {
      setError(e instanceof Error ? e.message : "Could not load sources");
    });
  }, [refresh]);

  const disabledReasons = useMemo(() => {
    const reasons = Object.values(statuses)
      .map((status) => status.disabled_reason)
      .filter((reason): reason is string => Boolean(reason));
    return Array.from(new Set(reasons));
  }, [statuses]);

  async function connect(connector: Connector) {
    setBusy(connector.provider);
    setError(null);
    try {
      await startConnect(connector.provider, returnTo);
    } catch (e) {
      if (e instanceof ApiError && e.status === 402) {
        setPaymentRequired(true);
      } else {
        setError(e instanceof Error ? e.message : "Could not start connection");
      }
      setBusy(null);
    }
  }

  async function submitCreds(connector: Connector, values: Record<string, string>) {
    setBusy(connector.provider);
    setError(null);
    try {
      await submitCredentials(connector.provider, values);
      setExpanded(null);
      await refresh();
      return true;
    } catch (e) {
      if (e instanceof ApiError && e.status === 402) {
        setPaymentRequired(true);
      } else {
        setError(e instanceof Error ? e.message : "Could not connect");
      }
      return false;
    } finally {
      setBusy(null);
    }
  }

  async function disconnect(connector: Connector) {
    const ok = await confirm({
      title: `Disconnect ${connector.label}?`,
      body: "You'll need to reconnect to sync its sources again.",
      confirmLabel: "Disconnect",
    });
    if (!ok) return;
    setBusy(connector.provider);
    setError(null);
    try {
      await disconnectIntegration(connector.provider);
      await refresh();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not disconnect");
    } finally {
      setBusy(null);
    }
  }

  return (
    <div className="space-y-2">
      {disabledReasons.length > 0 && (
        <div className="rounded-md border border-border bg-base px-3 py-2 text-[12px] text-muted">
          {disabledReasons.length === 1
            ? disabledReasons[0]
            : "Some integrations need server configuration before they can be connected."}
        </div>
      )}

      {CONNECTORS.map((connector) => {
        const status = statuses[connector.provider];
        const connected = !!status?.connected;
        const enabled = status?.enabled ?? true;
        return (
          <div key={connector.provider} className="rounded-lg border border-border bg-surface px-3 py-2.5">
            <div className="flex items-center gap-3">
              <span className="flex h-5 w-5 shrink-0 items-center justify-center">
                {connectorIcon(connector.provider)}
              </span>
              <div className="min-w-0 flex-1">
                <div className="text-[13.5px] font-medium text-foreground">{connector.label}</div>
                <div className="truncate text-[11.5px] text-muted">
                  {connected ? connectedLabel(status) : connector.blurb}
                </div>
              </div>
              <div className="flex shrink-0 items-center gap-2">
                <ConnectorAction
                  connector={connector}
                  connected={connected}
                  enabled={enabled}
                  authKind={status?.auth_kind ?? "oauth"}
                  disabledReason={status?.disabled_reason ?? null}
                  busy={busy === connector.provider}
                  workspaceId={workspaceId}
                  expanded={expanded === connector.provider}
                  onConnect={() => void connect(connector)}
                  onDisconnect={() => void disconnect(connector)}
                  onExpand={() =>
                    setExpanded((value) => (value === connector.provider ? null : connector.provider))
                  }
                />
              </div>
            </div>

            {expanded === connector.provider &&
              !connected &&
              status?.auth_kind === "api_key" &&
              status.credential_fields && (
                <CredentialForm
                  fields={status.credential_fields}
                  busy={busy === connector.provider}
                  onSubmit={(values) => submitCreds(connector, values)}
                />
              )}
          </div>
        );
      })}

      {includeObsidian && workspaceId && (
        <ObsidianSourceCard workspaceId={workspaceId} onUploaded={onObsidianUploaded} />
      )}

      {error && (
        <div className="rounded-md border border-error/30 bg-error/10 px-3 py-2 text-[12px] text-error">
          {error}
        </div>
      )}

      {paymentRequired && <PaywallModal onClose={() => setPaymentRequired(false)} />}
    </div>
  );
}

function connectedLabel(status: IntegrationStatus | undefined): string {
  const accounts = status?.accounts ?? [];
  if (accounts.length > 1) return `${accounts.length} accounts connected`;
  const account = status?.account_email || status?.account_display_name;
  if (account) return `Connected as ${account}`;
  return "Connected";
}

function ConnectorAction({
  connector,
  connected,
  enabled,
  authKind,
  disabledReason,
  busy,
  workspaceId,
  expanded,
  onConnect,
  onDisconnect,
  onExpand,
}: {
  connector: Connector;
  connected: boolean;
  enabled: boolean;
  authKind: IntegrationStatus["auth_kind"];
  disabledReason: string | null;
  busy: boolean;
  workspaceId: string | null;
  expanded: boolean;
  onConnect: () => void;
  onDisconnect: () => void;
  onExpand: () => void;
}) {
  if (!enabled) {
    return (
      <button type="button" disabled title={disabledReason ?? undefined} className={secondaryButton()}>
        Unavailable
      </button>
    );
  }
  if (!connected) {
    // api_key providers (Gong) reveal an inline credential form instead of
    // redirecting to an OAuth consent screen.
    if (authKind === "api_key") {
      return (
        <button type="button" onClick={onExpand} disabled={busy} className={primaryButton()}>
          {expanded ? "Cancel" : "Connect"}
        </button>
      );
    }
    return (
      <button type="button" onClick={onConnect} disabled={busy} className={primaryButton()}>
        {busy ? "Connecting..." : "Connect"}
      </button>
    );
  }
  return (
    <>
      {workspaceId && (
        <Link href={`/workspaces/${workspaceId}/integrations/${connector.provider}`} className={secondaryButton()}>
          Open
        </Link>
      )}
      <button
        type="button"
        onClick={onDisconnect}
        disabled={busy}
        className="cursor-pointer rounded-lg px-3 py-1.5 text-[12px] font-semibold text-muted hover:bg-raised hover:text-foreground disabled:opacity-60"
      >
        {busy ? "Disconnecting..." : "Disconnect"}
      </button>
    </>
  );
}

function ObsidianSourceCard({
  workspaceId,
  onUploaded,
}: {
  workspaceId: string;
  onUploaded?: () => void;
}) {
  const [open, setOpen] = useState(false);
  return (
    <div className="rounded-lg border border-border bg-surface px-3 py-2.5">
      <div className="flex items-center gap-3">
        <span className="flex h-5 w-5 shrink-0 items-center justify-center">
          <ObsidianIcon />
        </span>
        <div className="min-w-0 flex-1">
          <div className="text-[13.5px] font-medium text-foreground">Obsidian vault</div>
          <div className="truncate text-[11.5px] text-muted">Upload a vault into Files.</div>
        </div>
        <button type="button" onClick={() => setOpen((value) => !value)} className={secondaryButton()}>
          {open ? "Hide" : "Upload vault"}
        </button>
      </div>
      {open && (
        <div className="mt-3">
          <ObsidianVaultDropZone workspaceId={workspaceId} onUploaded={onUploaded ?? (() => {})} />
        </div>
      )}
    </div>
  );
}
