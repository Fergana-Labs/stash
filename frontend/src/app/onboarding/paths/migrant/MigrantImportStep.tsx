"use client";

import { useCallback, useEffect, useState } from "react";

import IntegrationCard from "@/components/integrations/IntegrationCard";
import DriveImportDialog from "@/components/import/DriveImportDialog";
import GitImportDialog from "@/components/import/GitImportDialog";
import NotionImportDialog from "@/components/import/NotionImportDialog";
import StashQuickAdd from "@/components/StashQuickAdd";
import { IntegrationStatus, listIntegrations } from "@/lib/integrations";
import type { StepCtx } from "@/lib/onboarding/paths";

const RETURN_TO = "/onboarding?path=migrant&step=2";

export default function MigrantImportStep({ source, workspaceId }: StepCtx) {
  if (!source) {
    return (
      <div className="text-sm text-muted">
        Pick a source first — go back to the previous step.
      </div>
    );
  }

  if (source === "obsidian") return <ObsidianBlock workspaceId={workspaceId} />;
  return <ProviderBlock source={source} workspaceId={workspaceId} />;
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
}: {
  source: ProviderSource;
  workspaceId: string | null;
}) {
  const [providers, setProviders] = useState<IntegrationStatus[] | null>(null);
  const [showDialog, setShowDialog] = useState(false);

  const { heading, subhead, integrationKey } = PROVIDER_COPY[source];

  const refresh = useCallback(async () => {
    const r = await listIntegrations();
    setProviders(r.providers);
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

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
        <IntegrationCard status={provider} onChanged={refresh} returnTo={RETURN_TO} />
      )}

      {isConnected && workspaceId && (
        <button
          type="button"
          onClick={() => setShowDialog(true)}
          className="rounded-md bg-brand px-4 py-2 text-[13px] font-medium text-white hover:bg-brand-hover"
        >
          Pick what to import →
        </button>
      )}

      {showDialog && workspaceId && source === "notion" && (
        <NotionImportDialog
          workspaceId={workspaceId}
          onDispatched={() => setShowDialog(false)}
          onClose={() => setShowDialog(false)}
        />
      )}
      {showDialog && workspaceId && source === "github" && (
        <GitImportDialog
          workspaceId={workspaceId}
          onDispatched={() => setShowDialog(false)}
          onClose={() => setShowDialog(false)}
        />
      )}
      {showDialog && workspaceId && source === "drive" && (
        <DriveImportDialog
          workspaceId={workspaceId}
          onDispatched={() => setShowDialog(false)}
          onClose={() => setShowDialog(false)}
        />
      )}
    </div>
  );
}

function ObsidianBlock({ workspaceId }: { workspaceId: string | null }) {
  return (
    <div className="space-y-6">
      <div className="space-y-2">
        <h1 className="font-display text-[28px] leading-[1.1] font-bold tracking-tight text-foreground">
          Drop your vault
        </h1>
        <p className="text-sm text-dim max-w-md">
          Drag your Obsidian vault folder right onto the drop zone below.
          Folders become folders, every <code>.md</code> becomes a
          collaboratively-edited page.
        </p>
      </div>

      {workspaceId && <StashQuickAdd workspaceId={workspaceId} />}

      <div className="rounded-xl border border-border-subtle bg-background/40 p-4 space-y-2 text-[12px] text-muted leading-relaxed">
        <div className="font-medium text-foreground">How to get your vault</div>
        <ol className="list-decimal pl-5 space-y-1">
          <li>
            In Finder / File Explorer, find your vault folder (the one
            containing your <code>.md</code> files).
          </li>
          <li>
            Drag the whole folder onto the drop zone above. Or use the
            &ldquo;Upload folder&rdquo; button.
          </li>
          <li>
            Plugins and <code>.obsidian/</code> config are ignored — only
            <code>.md</code> and other regular files get imported.
          </li>
        </ol>
      </div>
    </div>
  );
}
