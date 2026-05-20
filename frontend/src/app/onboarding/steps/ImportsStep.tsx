"use client";

import { useCallback, useEffect, useState } from "react";

import IntegrationCard from "@/components/integrations/IntegrationCard";
import DriveImportDialog from "@/components/import/DriveImportDialog";
import GitImportDialog from "@/components/import/GitImportDialog";
import NotionImportDialog from "@/components/import/NotionImportDialog";
import { IntegrationStatus, listIntegrations } from "@/lib/integrations";

type Props = {
  workspaceId: string | null;
};

type DialogKind = "github" | "google" | "notion" | null;

const RETURN_TO = "/onboarding?step=3";

export default function ImportsStep({ workspaceId }: Props) {
  const [providers, setProviders] = useState<IntegrationStatus[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [dialog, setDialog] = useState<DialogKind>(null);
  const [dispatchedCount, setDispatchedCount] = useState(0);

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

  // Re-fetch when the user returns from the OAuth callback; strip the
  // ?connected=… query so a manual refresh doesn't keep firing.
  useEffect(() => {
    if (typeof window === "undefined") return;
    const params = new URLSearchParams(window.location.search);
    if (params.get("connected")) {
      void refresh();
      const url = new URL(window.location.href);
      url.searchParams.delete("connected");
      window.history.replaceState({}, "", url.pathname + url.search);
    }
  }, [refresh]);

  const byProvider = new Map(providers?.map((p) => [p.provider, p]) ?? []);

  return (
    <div className="space-y-6">
      <div className="space-y-2">
        <h1 className="font-display text-[28px] leading-[1.1] font-bold tracking-tight text-foreground">
          Connect a source
        </h1>
        <p className="text-sm text-dim max-w-md">
          Pull existing docs from GitHub, Google Drive, or Notion into your
          workspace. Connect now or skip and do it later from Settings.
        </p>
      </div>

      {error && (
        <div className="text-[12px] text-error rounded-lg border border-error/30 bg-error/10 px-3 py-2">
          {error}
        </div>
      )}

      {providers === null ? (
        <div className="text-[12px] text-muted">Loading…</div>
      ) : (
        <div className="space-y-3">
          {providers.map((p) => (
            <div key={p.provider} className="space-y-2">
              <IntegrationCard status={p} onChanged={refresh} returnTo={RETURN_TO} />
              {p.connected && workspaceId && (
                <div className="pl-14">
                  <button
                    type="button"
                    onClick={() => setDialog(p.provider as DialogKind)}
                    className="text-[12px] font-medium text-brand hover:text-brand-hover"
                  >
                    Import from {p.display_name} →
                  </button>
                </div>
              )}
            </div>
          ))}
        </div>
      )}

      {dispatchedCount > 0 && (
        <div className="text-[12px] text-muted rounded-lg border border-border-subtle bg-background/40 px-3 py-2">
          {dispatchedCount} import{dispatchedCount === 1 ? "" : "s"} running in
          the background. They&rsquo;ll appear in your workspace when ready.
        </div>
      )}

      {dialog === "github" && workspaceId && (
        <GitImportDialog
          workspaceId={workspaceId}
          onDispatched={(ids) => setDispatchedCount((n) => n + ids.length)}
          onClose={() => setDialog(null)}
        />
      )}
      {dialog === "google" && workspaceId && (
        <DriveImportDialog
          workspaceId={workspaceId}
          onDispatched={(ids) => setDispatchedCount((n) => n + ids.length)}
          onClose={() => setDialog(null)}
        />
      )}
      {dialog === "notion" && workspaceId && (
        <NotionImportDialog
          workspaceId={workspaceId}
          onDispatched={(ids) => setDispatchedCount((n) => n + ids.length)}
          onClose={() => setDialog(null)}
        />
      )}
    </div>
  );
}
