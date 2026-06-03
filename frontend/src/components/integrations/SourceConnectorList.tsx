"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import type { ReactNode } from "react";

import {
  addWorkspaceSource,
  deleteWorkspaceSource,
  listWorkspaceSources,
  syncWorkspaceSource,
  type WorkspaceSource,
} from "@/lib/api";
import {
  listGitHubRepos,
  listIntegrations,
  listNotionPages,
  startConnect,
  type GitHubRepoSummary,
  type IntegrationProvider,
  type IntegrationStatus,
  type NotionPageSummary,
} from "@/lib/integrations";

import {
  GitHubIcon,
  GoogleDriveIcon,
  GranolaIcon,
  NotionIcon,
  ObsidianIcon,
  SlackIcon,
} from "./BrandIcons";
import ObsidianVaultDropZone from "./ObsidianVaultDropZone";

type ConnectorKind = "github" | "drive" | "notion" | "auto";

type Connector = {
  provider: IntegrationProvider;
  label: string;
  sourceType: string;
  icon: ReactNode;
  kind: ConnectorKind;
  blurb: string;
};

type Props = {
  workspaceId: string | null;
  returnTo: string;
  includeObsidian?: boolean;
  onSourceCountChange?: (count: number) => void;
  onObsidianUploaded?: () => void;
};

const CONNECTORS: Connector[] = [
  {
    provider: "github",
    label: "GitHub",
    sourceType: "github_repo",
    icon: <GitHubIcon />,
    kind: "github",
    blurb: "Pick repos your agent can navigate.",
  },
  {
    provider: "google",
    label: "Google Drive",
    sourceType: "google_drive",
    icon: <GoogleDriveIcon />,
    kind: "drive",
    blurb: "Index My Drive and read docs on demand.",
  },
  {
    provider: "notion",
    label: "Notion",
    sourceType: "notion",
    icon: <NotionIcon />,
    kind: "notion",
    blurb: "Pick pages or databases shared with Stash.",
  },
  {
    provider: "slack",
    label: "Slack",
    sourceType: "slack",
    icon: <SlackIcon />,
    kind: "auto",
    blurb: "Channel history, kept in sync.",
  },
  {
    provider: "granola",
    label: "Granola",
    sourceType: "granola",
    icon: <GranolaIcon />,
    kind: "auto",
    blurb: "Meeting notes and transcripts.",
  },
];

export default function SourceConnectorList({
  workspaceId,
  returnTo,
  includeObsidian = true,
  onSourceCountChange,
  onObsidianUploaded,
}: Props) {
  const [statuses, setStatuses] = useState<Record<string, IntegrationStatus>>({});
  const [sources, setSources] = useState<WorkspaceSource[]>([]);
  const [expanded, setExpanded] = useState<IntegrationProvider | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    setError(null);
    const integrations = await listIntegrations();
    const nextStatuses: Record<string, IntegrationStatus> = {};
    for (const provider of integrations.providers) {
      nextStatuses[provider.provider] = provider;
    }
    setStatuses(nextStatuses);

    if (!workspaceId) {
      setSources([]);
      return;
    }
    setSources(await listWorkspaceSources(workspaceId));
  }, [workspaceId]);

  useEffect(() => {
    refresh().catch((e) => {
      setError(e instanceof Error ? e.message : "Could not load sources");
    });
  }, [refresh]);

  useEffect(() => {
    onSourceCountChange?.(sources.length);
  }, [onSourceCountChange, sources.length]);

  async function addSource(connector: Connector, body?: { external_ref?: string; display_name?: string }) {
    if (!workspaceId) return false;
    setBusy(connector.provider);
    setError(null);
    try {
      await addWorkspaceSource(workspaceId, {
        source_type: connector.sourceType,
        ...body,
      });
      setExpanded(null);
      await refresh();
      return true;
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not add source");
      return false;
    } finally {
      setBusy(null);
    }
  }

  async function syncSource(source: WorkspaceSource) {
    if (!workspaceId) return;
    setBusy(`sync:${source.source}`);
    setError(null);
    try {
      await syncWorkspaceSource(workspaceId, source.source);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not start sync");
    } finally {
      setBusy(null);
    }
  }

  async function removeSource(source: WorkspaceSource) {
    if (!workspaceId) return;
    if (!confirm(`Remove ${source.display_name}?`)) return;
    setBusy(`delete:${source.source}`);
    setError(null);
    try {
      await deleteWorkspaceSource(workspaceId, source.source);
      await refresh();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not remove source");
    } finally {
      setBusy(null);
    }
  }

  return (
    <div className="space-y-2">
      {CONNECTORS.map((connector) => {
        const status = statuses[connector.provider];
        const connected = !!status?.connected;
        const count = sources.filter((source) => source.type === connector.sourceType).length;
        return (
          <div key={connector.provider} className="rounded-lg border border-border bg-surface px-3 py-2.5">
            <div className="flex items-center gap-3">
              <span className="flex h-5 w-5 shrink-0 items-center justify-center">
                {connector.icon}
              </span>
              <div className="min-w-0 flex-1">
                <div className="text-[13.5px] font-medium text-foreground">
                  {connector.label}
                  {count > 0 && (
                    <span className="ml-1.5 text-[11px] font-normal text-muted">
                      · {count} added
                    </span>
                  )}
                </div>
                <div className="truncate text-[11.5px] text-muted">{connector.blurb}</div>
              </div>
              <ConnectorAction
                connector={connector}
                connected={connected}
                busy={busy === connector.provider}
                workspaceReady={!!workspaceId}
                expanded={expanded === connector.provider}
                onConnect={() => void startConnect(connector.provider, returnTo)}
                onExpand={() => setExpanded((value) => value === connector.provider ? null : connector.provider)}
                onAdd={() => void addSource(connector, connector.kind === "drive" ? {
                  external_ref: "root",
                  display_name: "Google Drive",
                } : undefined)}
              />
            </div>

            {expanded === connector.provider && connector.kind === "github" && workspaceId && (
              <GitHubRepoPicker
                busy={busy}
                onAdd={(repo) => addSource(connector, {
                  external_ref: repo.full_name,
                  display_name: repo.full_name,
                })}
              />
            )}
            {expanded === connector.provider && connector.kind === "notion" && workspaceId && (
              <NotionPagePicker
                busy={busy}
                onAdd={(page) => addSource(connector, {
                  external_ref: page.id,
                  display_name: page.title || page.id,
                })}
              />
            )}
          </div>
        );
      })}

      {sources.length > 0 && (
        <div className="rounded-lg border border-border bg-surface px-3 py-2.5">
          <div className="mb-2 text-[12px] font-medium text-foreground">Connected sources</div>
          <div className="space-y-1">
            {sources.map((source) => (
              <div key={source.source} className="flex items-center gap-2 rounded-md bg-base px-2 py-1.5">
                <div className="min-w-0 flex-1">
                  <div className="truncate text-[12.5px] text-foreground">{source.display_name}</div>
                  <div className="text-[11px] text-muted">{labelForSourceType(source.type)}</div>
                </div>
                <button
                  type="button"
                  disabled={busy === `sync:${source.source}`}
                  onClick={() => void syncSource(source)}
                  className="rounded-md border border-border px-2 py-1 text-[11.5px] text-muted hover:text-foreground disabled:opacity-60"
                >
                  {busy === `sync:${source.source}` ? "Syncing..." : "Sync"}
                </button>
                <button
                  type="button"
                  disabled={busy === `delete:${source.source}`}
                  onClick={() => void removeSource(source)}
                  className="rounded-md border border-border px-2 py-1 text-[11.5px] text-muted hover:text-error disabled:opacity-60"
                >
                  Remove
                </button>
              </div>
            ))}
          </div>
        </div>
      )}

      {includeObsidian && workspaceId && (
        <ObsidianSourceCard workspaceId={workspaceId} onUploaded={onObsidianUploaded} />
      )}

      {error && (
        <div className="rounded-md border border-error/30 bg-error/10 px-3 py-2 text-[12px] text-error">
          {error}
        </div>
      )}
    </div>
  );
}

function ConnectorAction({
  connector,
  connected,
  busy,
  workspaceReady,
  expanded,
  onConnect,
  onExpand,
  onAdd,
}: {
  connector: Connector;
  connected: boolean;
  busy: boolean;
  workspaceReady: boolean;
  expanded: boolean;
  onConnect: () => void;
  onExpand: () => void;
  onAdd: () => void;
}) {
  if (!connected) {
    return (
      <button type="button" onClick={onConnect} className={primaryButton()}>
        Connect
      </button>
    );
  }
  if (connector.kind === "github") {
    return (
      <button type="button" onClick={onExpand} disabled={!workspaceReady} className={secondaryButton()}>
        {expanded ? "Hide repos" : "Add repo"}
      </button>
    );
  }
  if (connector.kind === "notion") {
    return (
      <button type="button" onClick={onExpand} disabled={!workspaceReady} className={secondaryButton()}>
        {expanded ? "Hide pages" : "Add page"}
      </button>
    );
  }
  if (connector.kind === "drive") {
    return (
      <button type="button" onClick={onAdd} disabled={!workspaceReady || busy} className={secondaryButton()}>
        {busy ? "Adding..." : "Add My Drive"}
      </button>
    );
  }
  return (
    <button type="button" onClick={onAdd} disabled={!workspaceReady || busy} className={secondaryButton()}>
      {busy ? "Adding..." : "Add"}
    </button>
  );
}

function GitHubRepoPicker({
  busy,
  onAdd,
}: {
  busy: string | null;
  onAdd: (repo: GitHubRepoSummary) => Promise<boolean>;
}) {
  const [repos, setRepos] = useState<GitHubRepoSummary[] | null>(null);
  const [query, setQuery] = useState("");
  const [error, setError] = useState("");

  useEffect(() => {
    let cancelled = false;
    listGitHubRepos()
      .then((next) => {
        if (!cancelled) setRepos(next);
      })
      .catch((e) => {
        if (!cancelled) setError(e instanceof Error ? e.message : "Could not load repos");
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return repos ?? [];
    return (repos ?? []).filter((repo) =>
      repo.full_name.toLowerCase().includes(q) ||
      (repo.description ?? "").toLowerCase().includes(q)
    );
  }, [query, repos]);

  return (
    <PickerShell
      error={error}
      loading={repos === null && !error}
      query={query}
      placeholder="Search repositories..."
      onQuery={setQuery}
      empty="No repositories found."
    >
      {filtered.map((repo) => (
        <button
          key={repo.full_name}
          type="button"
          disabled={busy === "github"}
          onClick={() => void onAdd(repo)}
          className="flex w-full items-start gap-2 rounded-md px-2 py-1.5 text-left hover:bg-raised disabled:opacity-60"
        >
          <GitHubIcon className="mt-0.5 text-muted" size={14} />
          <span className="min-w-0 flex-1">
            <span className="block truncate text-[12.5px] font-medium text-foreground">
              {repo.full_name}
            </span>
            {repo.description && (
              <span className="block truncate text-[11.5px] text-muted">{repo.description}</span>
            )}
          </span>
        </button>
      ))}
    </PickerShell>
  );
}

function NotionPagePicker({
  busy,
  onAdd,
}: {
  busy: string | null;
  onAdd: (page: NotionPageSummary) => Promise<boolean>;
}) {
  const [pages, setPages] = useState<NotionPageSummary[] | null>(null);
  const [query, setQuery] = useState("");
  const [error, setError] = useState("");

  useEffect(() => {
    let cancelled = false;
    listNotionPages()
      .then((next) => {
        if (!cancelled) setPages(next);
      })
      .catch((e) => {
        if (!cancelled) setError(e instanceof Error ? e.message : "Could not load pages");
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return pages ?? [];
    return (pages ?? []).filter((page) => page.title.toLowerCase().includes(q));
  }, [query, pages]);

  return (
    <PickerShell
      error={error}
      loading={pages === null && !error}
      query={query}
      placeholder="Search Notion pages..."
      onQuery={setQuery}
      empty="No shared Notion pages found."
    >
      {filtered.map((page) => (
        <button
          key={page.id}
          type="button"
          disabled={busy === "notion"}
          onClick={() => void onAdd(page)}
          className="flex w-full items-start gap-2 rounded-md px-2 py-1.5 text-left hover:bg-raised disabled:opacity-60"
        >
          <NotionIcon className="mt-0.5 text-muted" size={14} />
          <span className="min-w-0 flex-1">
            <span className="block truncate text-[12.5px] font-medium text-foreground">
              {page.title || "Untitled"}
            </span>
            <span className="block truncate text-[11.5px] text-muted">{page.url}</span>
          </span>
        </button>
      ))}
    </PickerShell>
  );
}

function PickerShell({
  error,
  loading,
  query,
  placeholder,
  empty,
  onQuery,
  children,
}: {
  error: string;
  loading: boolean;
  query: string;
  placeholder: string;
  empty: string;
  onQuery: (value: string) => void;
  children: ReactNode;
}) {
  const hasChildren = Array.isArray(children) ? children.length > 0 : !!children;
  return (
    <div className="mt-2.5 rounded-md border border-border bg-base p-2">
      <input
        type="search"
        value={query}
        onChange={(e) => onQuery(e.target.value)}
        placeholder={placeholder}
        className="mb-2 w-full rounded-md border border-border bg-surface px-2 py-1.5 text-[12px] text-foreground placeholder:text-muted focus:border-brand focus:outline-none"
      />
      {error ? (
        <div className="rounded-md bg-error/10 px-2 py-1.5 text-[11.5px] text-error">{error}</div>
      ) : loading ? (
        <div className="px-2 py-3 text-[12px] text-muted">Loading...</div>
      ) : hasChildren ? (
        <div className="max-h-48 overflow-y-auto">{children}</div>
      ) : (
        <div className="px-2 py-3 text-[12px] text-muted">{empty}</div>
      )}
    </div>
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

function labelForSourceType(type: string): string {
  if (type === "github_repo") return "GitHub";
  if (type === "google_drive") return "Google Drive";
  if (type === "notion") return "Notion";
  if (type === "slack") return "Slack";
  if (type === "granola") return "Granola";
  return type;
}

function primaryButton(): string {
  return "shrink-0 rounded-md bg-brand px-3 py-1.5 text-[12px] font-medium text-white hover:bg-brand-hover";
}

function secondaryButton(): string {
  return "shrink-0 rounded-md border border-border px-3 py-1.5 text-[12px] font-medium text-foreground hover:bg-raised disabled:opacity-60";
}
