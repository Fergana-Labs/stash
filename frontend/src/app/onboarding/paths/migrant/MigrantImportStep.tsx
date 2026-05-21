"use client";

import { useCallback, useEffect, useState } from "react";

import IntegrationCard from "@/components/integrations/IntegrationCard";
import DriveImportDialog from "@/components/import/DriveImportDialog";
import GitImportDialog from "@/components/import/GitImportDialog";
import NotionImportDialog from "@/components/import/NotionImportDialog";
import ObsidianVaultDropZone from "@/components/import/ObsidianVaultDropZone";
import { track } from "@/lib/analytics";
import { IntegrationStatus, listIntegrations } from "@/lib/integrations";
import type { MigrantSource, StepCtx } from "@/lib/onboarding/paths";

function returnToForSource(source: MigrantSource): string {
  // OAuth callback redirects here. Must carry source through, otherwise the
  // step boots into "Pick a source first."
  return `/onboarding?path=migrant&step=2&source=${source}`;
}

export default function MigrantImportStep(ctx: StepCtx) {
  const { source, workspaceId, setCanContinue } = ctx;

  // Continue stays disabled until the user has dispatched an import (or
  // finished a vault upload). The wizard resets canContinue=true on each
  // step transition; we re-disable here as long as no import has fired.
  useEffect(() => {
    setCanContinue(false);
  }, [setCanContinue]);

  function markImported() {
    track("onboarding.import_dispatched", {
      source,
      import_type: source === "obsidian" ? "vault_upload" : "oauth_dialog",
    });
    setCanContinue(true);
  }

  if (!source) {
    return (
      <div className="text-sm text-muted">
        Pick a source first — go back to the previous step.
      </div>
    );
  }

  if (source === "obsidian")
    return (
      <ObsidianBlock workspaceId={workspaceId} onUploaded={markImported} />
    );
  return (
    <ProviderBlock
      source={source}
      workspaceId={workspaceId}
      onDispatched={markImported}
    />
  );
}

type ProviderSource = "notion" | "github" | "drive";

const PROVIDER_COPY: Record<
  ProviderSource,
  { heading: string; subhead: string; integrationKey: string }
> = {
  notion: {
    heading: "Bring your Notion in",
    subhead: "Connect Notion, then pick what to import.",
    integrationKey: "notion",
  },
  github: {
    heading: "Bring your repo in",
    subhead:
      "Connect GitHub, then pick a repo. Everything's searchable and editable.",
    integrationKey: "github",
  },
  drive: {
    heading: "Bring your Drive in",
    subhead:
      "Connect Google, then pick what to bring over. Docs and Sheets included.",
    integrationKey: "google",
  },
};

function ProviderBlock({
  source,
  workspaceId,
  onDispatched,
}: {
  source: ProviderSource;
  workspaceId: string | null;
  onDispatched: () => void;
}) {
  const [providers, setProviders] = useState<IntegrationStatus[] | null>(null);
  const [showDialog, setShowDialog] = useState(false);
  const [dispatched, setDispatched] = useState(false);
  const returnTo = returnToForSource(source);

  const { heading, subhead, integrationKey } = PROVIDER_COPY[source];

  const refresh = useCallback(async () => {
    const r = await listIntegrations();
    setProviders(r.providers);
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  // Re-fetch integrations when the URL carries a fresh OAuth callback.
  // URL cleanup (stripping ?connected=, writing ?source=) is handled at
  // the page level — we just need to know to refresh.
  useEffect(() => {
    if (typeof window === "undefined") return;
    const params = new URLSearchParams(window.location.search);
    if (params.get("connected")) void refresh();
  }, [refresh]);

  const provider = providers?.find((p) => p.provider === integrationKey);
  const isConnected = provider?.connected ?? false;

  return (
    <div className="space-y-6">
      <div className="space-y-2">
        <h1 className="font-display text-[28px] leading-[1.1] font-bold tracking-tight text-foreground">
          {heading}
        </h1>
        <p className="text-sm text-dim max-w-md">{subhead}</p>
      </div>

      {provider && (
        <IntegrationCard status={provider} onChanged={refresh} returnTo={returnTo} />
      )}

      {isConnected && workspaceId && !dispatched && (
        <button
          type="button"
          onClick={() => setShowDialog(true)}
          className="rounded-md bg-brand px-4 py-2 text-[13px] font-medium text-white hover:bg-brand-hover"
        >
          Pick what to import →
        </button>
      )}

      {dispatched && (
        <div className="rounded-xl border border-brand bg-brand/5 px-4 py-3 flex items-start gap-3">
          <span
            className="flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-brand text-white text-[10px] font-bold"
            aria-hidden
          >
            ✓
          </span>
          <div className="text-[12.5px] text-foreground leading-relaxed">
            Your import is running in the background. Continue when
            you&rsquo;re ready — it&rsquo;ll keep going.
          </div>
        </div>
      )}

      {showDialog && workspaceId && source === "notion" && (
        <NotionImportDialog
          workspaceId={workspaceId}
          onDispatched={() => {
            setShowDialog(false);
            setDispatched(true);
            onDispatched();
          }}
          onClose={() => setShowDialog(false)}
        />
      )}
      {showDialog && workspaceId && source === "github" && (
        <GitImportDialog
          workspaceId={workspaceId}
          onDispatched={() => {
            setShowDialog(false);
            setDispatched(true);
            onDispatched();
          }}
          onClose={() => setShowDialog(false)}
        />
      )}
      {showDialog && workspaceId && source === "drive" && (
        <DriveImportDialog
          workspaceId={workspaceId}
          onDispatched={() => {
            setShowDialog(false);
            setDispatched(true);
            onDispatched();
          }}
          onClose={() => setShowDialog(false)}
        />
      )}
    </div>
  );
}

function ObsidianBlock({
  workspaceId,
  onUploaded,
}: {
  workspaceId: string | null;
  onUploaded: () => void;
}) {
  return (
    <div className="space-y-6">
      <div className="space-y-2">
        <h1 className="font-display text-[28px] leading-[1.1] font-bold tracking-tight text-foreground">
          Drop your vault
        </h1>
        <p className="text-sm text-dim max-w-md">
          Drag your Obsidian vault folder onto the drop zone, or click to
          pick it. Folder structure is preserved; every <code>.md</code>{" "}
          becomes a collaboratively-edited note.
        </p>
      </div>

      {workspaceId && (
        <ObsidianVaultDropZone
          workspaceId={workspaceId}
          onUploaded={onUploaded}
        />
      )}

      <div className="rounded-xl border border-border-subtle bg-background/40 p-4 space-y-2 text-[12px] text-muted leading-relaxed">
        <div className="font-medium text-foreground">
          Don&rsquo;t know where your vault is?
        </div>
        <ul className="list-disc pl-5 space-y-1">
          <li>
            In Obsidian: <strong>File</strong> menu → <strong>Show in
            system explorer</strong> (or right-click any note in the
            sidebar → <strong>Reveal in Finder/Explorer</strong>) opens
            the vault folder.
          </li>
          <li>
            Common default locations:{" "}
            <code>~/Documents/</code>,{" "}
            <code>~/iCloud Drive/Obsidian/</code>, or{" "}
            <code>~/Obsidian/</code>.
          </li>
          <li>
            The vault is the folder containing your{" "}
            <code>.md</code> notes — drop that whole folder.
          </li>
        </ul>
      </div>
    </div>
  );
}

