"use client";

import { useEffect, useMemo, useState } from "react";
import type { ReactNode } from "react";

import { addWorkspaceSource, ApiError } from "@/lib/api";
import {
  type IntegrationAccount,
  listAsanaProjects,
  listGitHubRepos,
  listJiraProjects,
  listNotionPages,
  listSlackChannels,
  type AsanaProjectSummary,
  type CredentialField,
  type GitHubRepoSummary,
  type JiraProjectSummary,
  type NotionPageSummary,
  type SlackChannelSummary,
} from "@/lib/integrations";

import PaywallModal from "../PaywallModal";
import { AsanaIcon, GitHubIcon, JiraIcon, NotionIcon, SlackIcon } from "./BrandIcons";
import type { Connector } from "./connectors";

type AddSourceBody = {
  external_ref?: string;
  display_name?: string;
  settings?: Record<string, unknown>;
};

export function primaryButton(): string {
  return "shrink-0 rounded-md bg-brand px-3 py-1.5 text-[12px] font-medium text-white hover:bg-brand-hover disabled:opacity-60";
}

export function secondaryButton(): string {
  return "shrink-0 rounded-md border border-border px-3 py-1.5 text-[12px] font-medium text-foreground hover:bg-raised disabled:opacity-60";
}

// Renders the right "add a specific project/page/repo" UI for a connector and
// calls addWorkspaceSource, then onAdded(). Connected-only — callers gate on it.
export function AddSourceControls({
  connector,
  workspaceId,
  connected,
  accounts = [],
  existingRefs = [],
  onAdded,
}: {
  connector: Connector;
  workspaceId: string;
  connected: boolean;
  accounts?: IntegrationAccount[];
  existingRefs?: string[];
  onAdded: () => void;
}) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [paymentRequired, setPaymentRequired] = useState(false);
  const [gongWorkspaceIds, setGongWorkspaceIds] = useState("");

  async function add(body?: AddSourceBody) {
    setBusy(true);
    setError("");
    setPaymentRequired(false);
    try {
      await addWorkspaceSource(workspaceId, {
        source_type: connector.sourceType,
        ...body,
      });
      onAdded();
      return true;
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not add source");
      setPaymentRequired(e instanceof ApiError && e.status === 402);
      return false;
    } finally {
      setBusy(false);
    }
  }

  const errorRow = error ? (
    <>
      <div className="rounded-md bg-error/10 px-2 py-1.5 text-[11.5px] text-error">{error}</div>
      {paymentRequired && <PaywallModal onClose={() => setPaymentRequired(false)} />}
    </>
  ) : null;

  if (connector.kind === "github") {
    return (
      <div className="space-y-2">
        <GitHubRepoPicker
          busy={busy}
          onAdd={(repo) => add({ external_ref: repo.full_name, display_name: repo.full_name })}
        />
        {errorRow}
      </div>
    );
  }

  if (connector.kind === "notion") {
    return (
      <div className="space-y-2">
        <NotionPagePicker
          busy={busy}
          onAdd={(page) => add({ external_ref: page.id, display_name: page.title || page.id })}
        />
        {errorRow}
      </div>
    );
  }

  if (connector.kind === "jira") {
    return (
      <div className="space-y-2">
        <JiraProjectPicker
          busy={busy}
          onAdd={(project) =>
            add({ external_ref: project.external_ref, display_name: `${project.name} (${project.key})` })
          }
        />
        {errorRow}
      </div>
    );
  }

  if (connector.kind === "asana") {
    return (
      <div className="space-y-2">
        <AsanaProjectPicker
          busy={busy}
          onAdd={(project) => add({ external_ref: project.gid, display_name: project.name })}
        />
        {errorRow}
      </div>
    );
  }

  if (connector.kind === "drive") {
    return (
      <div className="space-y-2">
        <button
          type="button"
          onClick={() => void add({ external_ref: "root", display_name: "Google Drive" })}
          disabled={busy}
          className={secondaryButton()}
        >
          {busy ? "Adding..." : "Add My Drive"}
        </button>
        {errorRow}
      </div>
    );
  }

  if (connector.sourceType === "gong_calls") {
    const ids = gongWorkspaceIds
      .split(",")
      .map((id) => id.trim())
      .filter(Boolean);
    return (
      <div className="space-y-2">
        {!connected && (
          <div className="text-[11.5px] text-muted">Connect Gong first to add it.</div>
        )}
        <input
          value={gongWorkspaceIds}
          onChange={(event) => setGongWorkspaceIds(event.target.value)}
          placeholder="Gong workspace IDs"
          className="w-full rounded-md border border-border bg-background px-2 py-1.5 text-[12px] text-foreground placeholder:text-muted"
          disabled={busy || !connected}
        />
        <button
          type="button"
          onClick={() =>
            void add({
              settings: { allowed_workspace_ids: ids },
            })
          }
          disabled={busy || !connected || ids.length === 0}
          className={secondaryButton()}
        >
          {busy ? "Adding..." : "Add"}
        </button>
        {errorRow}
      </div>
    );
  }

  if (connector.provider === "gmail") {
    return (
      <div className="space-y-2">
        {accounts.length === 0 ? (
          <div className="text-[11.5px] text-muted">Connect Gmail first to add a mailbox.</div>
        ) : (
          accounts.map((account) => {
            const label = account.account_email || account.account_display_name || account.account_key;
            const added = existingRefs.includes(account.account_key);
            return (
              <div key={account.account_key} className="flex items-center gap-3 rounded-lg border border-border px-3 py-2">
                <div className="min-w-0 flex-1">
                  <div className="truncate text-[13px] font-medium text-foreground">{label}</div>
                  <div className="text-[11.5px] text-muted">Mailbox</div>
                </div>
                <button
                  type="button"
                  onClick={() => void add({ external_ref: account.account_key, display_name: `Gmail (${label})` })}
                  disabled={busy || added}
                  className={secondaryButton()}
                >
                  {added ? "Added" : busy ? "Adding..." : "Add"}
                </button>
              </div>
            );
          })
        )}
        {errorRow}
      </div>
    );
  }

  if (connector.provider === "slack") {
    return (
      <div className="space-y-2">
        {connected ? (
          <SlackChannelPicker
            busy={busy}
            onAdd={(channelIds) =>
              add({
                settings: { allowed_channel_ids: channelIds },
              })
            }
          />
        ) : (
          <div className="text-[11.5px] text-muted">Connect Slack first to add it.</div>
        )}
        {errorRow}
      </div>
    );
  }

  // kind "auto" — granola/gong/snowflake. The backend resolves the ref.
  return (
    <div className="space-y-2">
      {!connected && (
        <div className="text-[11.5px] text-muted">Connect {connector.label} first to add it.</div>
      )}
      <button type="button" onClick={() => void add()} disabled={busy || !connected} className={secondaryButton()}>
        {busy ? "Adding..." : "Add"}
      </button>
      {errorRow}
    </div>
  );
}

export function SlackChannelPicker({
  busy,
  onAdd,
}: {
  busy: boolean;
  onAdd: (channelIds: string[]) => Promise<boolean>;
}) {
  const [channels, setChannels] = useState<SlackChannelSummary[] | null>(null);
  const [selectedIds, setSelectedIds] = useState<string[]>([]);
  const [query, setQuery] = useState("");
  const [error, setError] = useState("");

  useEffect(() => {
    let cancelled = false;
    listSlackChannels()
      .then((next) => {
        if (!cancelled) setChannels(next);
      })
      .catch((e) => {
        if (!cancelled) setError(e instanceof Error ? e.message : "Could not load channels");
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const selected = useMemo(() => new Set(selectedIds), [selectedIds]);
  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return channels ?? [];
    return (channels ?? []).filter(
      (channel) =>
        channel.name.toLowerCase().includes(q) || channel.id.toLowerCase().includes(q),
    );
  }, [query, channels]);

  function toggleChannel(channelId: string) {
    setSelectedIds((current) =>
      current.includes(channelId)
        ? current.filter((id) => id !== channelId)
        : [...current, channelId],
    );
  }

  return (
    <div>
      <PickerShell
        error={error}
        loading={channels === null && !error}
        query={query}
        placeholder="Search channels..."
        onQuery={setQuery}
        empty="No channels found."
      >
        {filtered.map((channel) => (
          <label
            key={channel.id}
            className="flex w-full items-start gap-2 rounded-md px-2 py-1.5 text-left hover:bg-raised"
          >
            <input
              type="checkbox"
              checked={selected.has(channel.id)}
              disabled={busy}
              onChange={() => toggleChannel(channel.id)}
              className="mt-0.5 h-3.5 w-3.5 shrink-0 rounded border-border"
            />
            <SlackIcon className="mt-0.5 shrink-0" size={14} />
            <span className="min-w-0 flex-1">
              <span className="block truncate text-[12.5px] font-medium text-foreground">
                {channel.name}
              </span>
              <span className="block truncate text-[11.5px] text-muted">
                {channel.is_private ? "Private" : "Channel"} · {channel.id}
              </span>
            </span>
          </label>
        ))}
      </PickerShell>
      <div className="mt-2 flex items-center justify-between gap-3">
        <div className="text-[11.5px] text-muted">{selectedIds.length} selected</div>
        <button
          type="button"
          disabled={busy || selectedIds.length === 0}
          onClick={() => void onAdd(selectedIds)}
          className={primaryButton()}
        >
          {busy ? "Adding..." : "Add"}
        </button>
      </div>
    </div>
  );
}

export function GitHubRepoPicker({
  busy,
  onAdd,
}: {
  busy: boolean;
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
    return (repos ?? []).filter(
      (repo) =>
        repo.full_name.toLowerCase().includes(q) ||
        (repo.description ?? "").toLowerCase().includes(q),
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
          disabled={busy}
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

export function NotionPagePicker({
  busy,
  onAdd,
}: {
  busy: boolean;
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
          disabled={busy}
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

export function JiraProjectPicker({
  busy,
  onAdd,
}: {
  busy: boolean;
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
          disabled={busy}
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

export function AsanaProjectPicker({
  busy,
  onAdd,
}: {
  busy: boolean;
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
          disabled={busy}
          onClick={() => void onAdd(project)}
          className="flex w-full items-start gap-2 rounded-md px-2 py-1.5 text-left hover:bg-raised disabled:opacity-60"
        >
          <AsanaIcon className="mt-0.5" size={14} />
          <span className="min-w-0 flex-1">
            <span className="block truncate text-[12.5px] font-medium text-foreground">
              {project.name}
            </span>
            <span className="block truncate text-[11.5px] text-muted">{project.workspace_name}</span>
          </span>
        </button>
      ))}
    </PickerShell>
  );
}

export function CredentialForm({
  fields,
  busy,
  onSubmit,
}: {
  fields: CredentialField[];
  busy: boolean;
  onSubmit: (values: Record<string, string>) => Promise<boolean>;
}) {
  const [values, setValues] = useState<Record<string, string>>({});
  // Only the required (non-optional) fields gate submission; "one of" auth
  // choices are marked optional and validated server-side.
  const complete = fields
    .filter((f) => !f.optional)
    .every((f) => (values[f.name] ?? "").trim().length > 0);

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
          <span className="mb-1 block text-[11.5px] text-muted">
            {field.label}
            {field.optional && <span className="ml-1 text-dim">(optional)</span>}
          </span>
          <input
            type={field.secret ? "password" : "text"}
            value={values[field.name] ?? ""}
            placeholder={field.placeholder}
            autoComplete="off"
            onChange={(e) => setValues((v) => ({ ...v, [field.name]: e.target.value }))}
            className="w-full rounded-md border border-border bg-surface px-2 py-1.5 text-[12px] text-foreground placeholder:text-muted focus:border-brand focus:outline-none"
          />
          {field.help && <span className="mt-1 block text-[11px] text-dim">{field.help}</span>}
        </label>
      ))}
      <button type="submit" disabled={!complete || busy} className={primaryButton()}>
        {busy ? "Connecting..." : "Connect"}
      </button>
    </form>
  );
}

export function PickerShell({
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
