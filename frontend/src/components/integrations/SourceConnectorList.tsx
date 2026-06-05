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
  listAsanaProjects,
  listGitHubRepos,
  listIntegrations,
  disconnectIntegration,
  listJiraProjects,
  listNotionPages,
  startConnect,
  submitCredentials,
  type AsanaProjectSummary,
  type CredentialField,
  type GitHubRepoSummary,
  type IntegrationProvider,
  type IntegrationStatus,
  type JiraProjectSummary,
  type NotionPageSummary,
} from "@/lib/integrations";

import {
  AsanaIcon,
  GitHubIcon,
  GongIcon,
  GoogleDriveIcon,
  GranolaIcon,
  JiraIcon,
  NotionIcon,
  ObsidianIcon,
  SlackIcon,
  SnowflakeIcon,
} from "./BrandIcons";
import ObsidianVaultDropZone from "./ObsidianVaultDropZone";

type ConnectorKind = "github" | "drive" | "notion" | "jira" | "asana" | "auto";

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
    provider: "jira",
    label: "Jira",
    sourceType: "jira_project",
    icon: <JiraIcon />,
    kind: "jira",
    blurb: "Search issues from a project.",
  },
  {
    provider: "asana",
    label: "Asana",
    sourceType: "asana_project",
    icon: <AsanaIcon />,
    kind: "asana",
    blurb: "Navigate tasks from a project.",
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
  {
    provider: "gong",
    label: "Gong",
    sourceType: "gong_calls",
    icon: <GongIcon />,
    kind: "auto",
    blurb: "Call transcripts, kept in sync.",
  },
  {
    provider: "snowflake",
    label: "Snowflake",
    sourceType: "snowflake",
    icon: <SnowflakeIcon />,
    kind: "auto",
    blurb: "Run read-only SQL against your warehouse.",
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

  const disabledReasons = useMemo(() => {
    const reasons = Object.values(statuses)
      .map((status) => status.disabled_reason)
      .filter((reason): reason is string => Boolean(reason));
    return Array.from(new Set(reasons));
  }, [statuses]);

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

  async function connect(connector: Connector) {
    setBusy(connector.provider);
    setError(null);
    try {
      await startConnect(connector.provider, returnTo);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not start connection");
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
      setError(e instanceof Error ? e.message : "Could not connect");
      return false;
    } finally {
      setBusy(null);
    }
  }

  async function disconnect(connector: Connector) {
    if (!confirm(`Disconnect ${connector.label}? You'll need to reconnect to sync its sources again.`)) {
      return;
    }
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
                <div className="truncate text-[11.5px] text-muted">
                  {connected && (status?.account_email || status?.account_display_name)
                    ? `Connected as ${status.account_email || status.account_display_name}`
                    : connector.blurb}
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
                  workspaceReady={!!workspaceId}
                  expanded={expanded === connector.provider}
                  onConnect={() => void connect(connector)}
                  onExpand={() => setExpanded((value) => value === connector.provider ? null : connector.provider)}
                  onAdd={() => void addSource(connector, connector.kind === "drive" ? {
                    external_ref: "root",
                    display_name: "Google Drive",
                  } : undefined)}
                />
                {connected && (
                  <button
                    type="button"
                    onClick={() => void disconnect(connector)}
                    disabled={busy === connector.provider}
                    title="Disconnect"
                    className="shrink-0 rounded-md border border-border px-2 py-1.5 text-[12px] font-medium text-muted hover:text-error hover:border-error/40 disabled:opacity-60"
                  >
                    Disconnect
                  </button>
                )}
              </div>
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
            {expanded === connector.provider && connector.kind === "jira" && workspaceId && (
              <JiraProjectPicker
                busy={busy}
                onAdd={(project) => addSource(connector, {
                  external_ref: project.external_ref,
                  display_name: `${project.name} (${project.key})`,
                })}
              />
            )}
            {expanded === connector.provider && connector.kind === "asana" && workspaceId && (
              <AsanaProjectPicker
                busy={busy}
                onAdd={(project) => addSource(connector, {
                  external_ref: project.gid,
                  display_name: project.name,
                })}
              />
            )}
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
  enabled,
  authKind,
  disabledReason,
  busy,
  workspaceReady,
  expanded,
  onConnect,
  onExpand,
  onAdd,
}: {
  connector: Connector;
  connected: boolean;
  enabled: boolean;
  authKind: IntegrationStatus["auth_kind"];
  disabledReason: string | null;
  busy: boolean;
  workspaceReady: boolean;
  expanded: boolean;
  onConnect: () => void;
  onExpand: () => void;
  onAdd: () => void;
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
  if (connector.kind === "jira" || connector.kind === "asana") {
    return (
      <button type="button" onClick={onExpand} disabled={!workspaceReady} className={secondaryButton()}>
        {expanded ? "Hide projects" : "Add project"}
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

function JiraProjectPicker({
  busy,
  onAdd,
}: {
  busy: string | null;
  onAdd: (project: JiraProjectSummary) => Promise<boolean>;
}) {
  const [projects, setProjects] = useState<JiraProjectSummary[] | null>(null);
  const [query, setQuery] = useState("");
  const [error, setError] = useState("");

  useEffect(() => {
    let cancelled = false;
    listJiraProjects()
      .then((next) => {
        if (!cancelled) setProjects(next);
      })
      .catch((e) => {
        if (!cancelled) setError(e instanceof Error ? e.message : "Could not load projects");
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return projects ?? [];
    return (projects ?? []).filter(
      (p) => p.name.toLowerCase().includes(q) || p.key.toLowerCase().includes(q),
    );
  }, [query, projects]);

  return (
    <PickerShell
      error={error}
      loading={projects === null && !error}
      query={query}
      placeholder="Search projects..."
      onQuery={setQuery}
      empty="No Jira projects found."
    >
      {filtered.map((project) => (
        <button
          key={project.external_ref}
          type="button"
          disabled={busy === "jira"}
          onClick={() => void onAdd(project)}
          className="flex w-full items-start gap-2 rounded-md px-2 py-1.5 text-left hover:bg-raised disabled:opacity-60"
        >
          <JiraIcon className="mt-0.5" size={14} />
          <span className="min-w-0 flex-1">
            <span className="block truncate text-[12.5px] font-medium text-foreground">
              {project.name} <span className="text-muted">({project.key})</span>
            </span>
            <span className="block truncate text-[11.5px] text-muted">{project.site_name}</span>
          </span>
        </button>
      ))}
    </PickerShell>
  );
}

function AsanaProjectPicker({
  busy,
  onAdd,
}: {
  busy: string | null;
  onAdd: (project: AsanaProjectSummary) => Promise<boolean>;
}) {
  const [projects, setProjects] = useState<AsanaProjectSummary[] | null>(null);
  const [query, setQuery] = useState("");
  const [error, setError] = useState("");

  useEffect(() => {
    let cancelled = false;
    listAsanaProjects()
      .then((next) => {
        if (!cancelled) setProjects(next);
      })
      .catch((e) => {
        if (!cancelled) setError(e instanceof Error ? e.message : "Could not load projects");
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return projects ?? [];
    return (projects ?? []).filter((p) => p.name.toLowerCase().includes(q));
  }, [query, projects]);

  return (
    <PickerShell
      error={error}
      loading={projects === null && !error}
      query={query}
      placeholder="Search projects..."
      onQuery={setQuery}
      empty="No Asana projects found."
    >
      {filtered.map((project) => (
        <button
          key={project.gid}
          type="button"
          disabled={busy === "asana"}
          onClick={() => void onAdd(project)}
          className="flex w-full items-start gap-2 rounded-md px-2 py-1.5 text-left hover:bg-raised disabled:opacity-60"
        >
          <AsanaIcon className="mt-0.5" size={14} />
          <span className="min-w-0 flex-1">
            <span className="block truncate text-[12.5px] font-medium text-foreground">
              {project.name}
            </span>
            <span className="block truncate text-[11.5px] text-muted">
              {project.workspace_name}
            </span>
          </span>
        </button>
      ))}
    </PickerShell>
  );
}

function CredentialForm({
  fields,
  busy,
  onSubmit,
}: {
  fields: CredentialField[];
  busy: boolean;
  onSubmit: (values: Record<string, string>) => Promise<boolean>;
}) {
  const [values, setValues] = useState<Record<string, string>>({});
  const complete = fields.every((f) => (values[f.name] ?? "").trim().length > 0);

  return (
    <form
      className="mt-2.5 space-y-2 rounded-md border border-border bg-base p-2"
      onSubmit={(e) => {
        e.preventDefault();
        if (complete) void onSubmit(values);
      }}
    >
      {fields.map((field) => (
        <label key={field.name} className="block">
          <span className="mb-1 block text-[11.5px] text-muted">{field.label}</span>
          <input
            type={field.secret ? "password" : "text"}
            value={values[field.name] ?? ""}
            placeholder={field.placeholder}
            autoComplete="off"
            onChange={(e) => setValues((v) => ({ ...v, [field.name]: e.target.value }))}
            className="w-full rounded-md border border-border bg-surface px-2 py-1.5 text-[12px] text-foreground placeholder:text-muted focus:border-brand focus:outline-none"
          />
        </label>
      ))}
      <button type="submit" disabled={!complete || busy} className={primaryButton()}>
        {busy ? "Connecting..." : "Connect"}
      </button>
    </form>
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
  if (type === "jira_project") return "Jira";
  if (type === "asana_project") return "Asana";
  if (type === "gong_calls") return "Gong";
  if (type === "snowflake") return "Snowflake";
  return type;
}

function primaryButton(): string {
  return "shrink-0 rounded-md bg-brand px-3 py-1.5 text-[12px] font-medium text-white hover:bg-brand-hover disabled:opacity-60";
}

function secondaryButton(): string {
  return "shrink-0 rounded-md border border-border px-3 py-1.5 text-[12px] font-medium text-foreground hover:bg-raised disabled:opacity-60";
}
