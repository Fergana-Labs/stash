"use client";

import { useCallback, useEffect, useState } from "react";

import { addWorkspaceSource, listWorkspaceSources, type WorkspaceSource } from "@/lib/api";
import {
  listIntegrations,
  startConnect,
  type IntegrationProvider,
  type IntegrationStatus,
} from "@/lib/integrations";

import { GitHubIcon, GoogleDriveIcon, NotionIcon, ObsidianIcon } from "./BrandIcons";
import ObsidianVaultDropZone from "./ObsidianVaultDropZone";

type Connector = {
  provider: IntegrationProvider;
  label: string;
  sourceType: string;
  icon: React.ReactNode;
  // Slack/Granola resolve their source from the token, so we add the source
  // right after connecting. Tree sources need a repo/folder pick (in Settings).
  autoAdd: boolean;
  blurb: string;
};

const DOT = (color: string) => (
  <span className="inline-block h-4 w-4 rounded-full" style={{ background: color }} />
);

const CONNECTORS: Connector[] = [
  { provider: "github", label: "GitHub", sourceType: "github_repo", icon: <GitHubIcon />, autoAdd: false, blurb: "Navigate repos like a filesystem." },
  { provider: "google", label: "Google Drive", sourceType: "google_drive", icon: <GoogleDriveIcon />, autoAdd: false, blurb: "Docs, indexed and read on demand." },
  { provider: "notion", label: "Notion", sourceType: "notion", icon: <NotionIcon />, autoAdd: false, blurb: "Pages and databases." },
  { provider: "slack", label: "Slack", sourceType: "slack", icon: DOT("#4a154b"), autoAdd: true, blurb: "Channel history, kept in sync." },
  { provider: "granola", label: "Granola", sourceType: "granola", icon: DOT("#e0700f"), autoAdd: true, blurb: "Meeting notes and transcripts." },
];

// A modal launcher for adding sources — separate from the full Settings page.
// Lists every source type with its current state so you can connect the ones
// you haven't set up yet.
export default function AddSourceModal({
  workspaceId,
  returnTo,
  onClose,
}: {
  workspaceId: string;
  returnTo: string;
  onClose: () => void;
}) {
  const [statuses, setStatuses] = useState<Record<string, IntegrationStatus> | null>(null);
  const [added, setAdded] = useState<WorkspaceSource[]>([]);
  const [showObsidian, setShowObsidian] = useState(false);
  const [busy, setBusy] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    const [ints, sources] = await Promise.all([
      listIntegrations().catch(() => ({ providers: [] as IntegrationStatus[] })),
      listWorkspaceSources(workspaceId).catch(() => [] as WorkspaceSource[]),
    ]);
    const map: Record<string, IntegrationStatus> = {};
    for (const p of ints.providers) map[p.provider] = p;
    setStatuses(map);
    setAdded(sources);
  }, [workspaceId]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  async function addSource(c: Connector) {
    setBusy(c.provider);
    try {
      await addWorkspaceSource(workspaceId, { source_type: c.sourceType });
      await refresh();
    } finally {
      setBusy(null);
    }
  }

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4"
      onClick={onClose}
    >
      <div
        className="scroll-thin max-h-[85vh] w-full max-w-lg overflow-y-auto rounded-2xl border border-border bg-base p-5 shadow-xl"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-start justify-between">
          <div>
            <h2 className="font-display text-[18px] font-bold text-foreground">Add a source</h2>
            <p className="mt-0.5 text-[12.5px] text-muted">
              Connect a source and your agent can read across it.
            </p>
          </div>
          <button
            type="button"
            onClick={onClose}
            aria-label="Close"
            className="rounded-md px-2 py-1 text-[18px] leading-none text-muted hover:bg-raised hover:text-foreground"
          >
            ×
          </button>
        </div>

        <div className="mt-4 space-y-2">
          {CONNECTORS.map((c) => {
            const connected = !!statuses?.[c.provider]?.connected;
            const count = added.filter((s) => s.type === c.sourceType).length;
            return (
              <div
                key={c.provider}
                className="flex items-center gap-3 rounded-lg border border-border bg-surface px-3 py-2.5"
              >
                <span className="flex h-5 w-5 shrink-0 items-center justify-center">{c.icon}</span>
                <div className="min-w-0 flex-1">
                  <div className="text-[13.5px] font-medium text-foreground">
                    {c.label}
                    {count > 0 && (
                      <span className="ml-1.5 text-[11px] font-normal text-muted">
                        · {count} added
                      </span>
                    )}
                  </div>
                  <div className="truncate text-[11.5px] text-muted">{c.blurb}</div>
                </div>
                {!connected ? (
                  <button
                    type="button"
                    onClick={() => void startConnect(c.provider, returnTo)}
                    className="shrink-0 rounded-md bg-brand px-3 py-1.5 text-[12px] font-medium text-white hover:bg-brand-hover"
                  >
                    Connect
                  </button>
                ) : c.autoAdd && count === 0 ? (
                  <button
                    type="button"
                    disabled={busy === c.provider}
                    onClick={() => void addSource(c)}
                    className="shrink-0 rounded-md border border-border px-3 py-1.5 text-[12px] font-medium text-foreground hover:bg-raised disabled:opacity-60"
                  >
                    {busy === c.provider ? "Adding…" : "Add"}
                  </button>
                ) : !c.autoAdd ? (
                  <a
                    href="/settings/integrations"
                    className="shrink-0 rounded-md border border-border px-3 py-1.5 text-[12px] font-medium text-foreground hover:bg-raised"
                  >
                    Add repo/folder
                  </a>
                ) : (
                  <span className="shrink-0 text-[12px] font-medium text-success">Connected ✓</span>
                )}
              </div>
            );
          })}

          {/* Obsidian is an upload, not a sync connector. */}
          <div className="rounded-lg border border-border bg-surface px-3 py-2.5">
            <div className="flex items-center gap-3">
              <span className="flex h-5 w-5 shrink-0 items-center justify-center"><ObsidianIcon /></span>
              <div className="min-w-0 flex-1">
                <div className="text-[13.5px] font-medium text-foreground">Obsidian vault</div>
                <div className="truncate text-[11.5px] text-muted">
                  Upload a vault — markdown lands in Files.
                </div>
              </div>
              <button
                type="button"
                onClick={() => setShowObsidian((v) => !v)}
                className="shrink-0 rounded-md border border-border px-3 py-1.5 text-[12px] font-medium text-foreground hover:bg-raised"
              >
                {showObsidian ? "Hide" : "Upload vault"}
              </button>
            </div>
            {showObsidian && (
              <div className="mt-3">
                <ObsidianVaultDropZone workspaceId={workspaceId} onUploaded={() => {}} />
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
