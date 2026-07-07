"use client";

import { useEffect, useMemo, useState } from "react";
import type { ReactNode } from "react";

import { addSource } from "@/lib/api";
import {
  type IntegrationAccount,
  getGitHubRepoAccess,
  listAsanaProjects,
  listGitHubRepos,
  listJiraProjects,
  listNotionPages,
  listSlackChannels,
  setGitHubRepoAccess,
  type AsanaProjectSummary,
  type CredentialField,
  type GitHubRepoAccess,
  type GitHubRepoSummary,
  type JiraProjectSummary,
  type NotionPageSummary,
  type SlackChannelSummary,
} from "@/lib/integrations";

import { AsanaIcon, GitHubIcon, JiraIcon, NotionIcon, SlackIcon } from "./BrandIcons";
import type { Connector } from "./connectors";

type AddSourceBody = {
  external_ref?: string;
  display_name?: string;
  settings?: Record<string, unknown>;
};

export function primaryButton(): string {
  return "shrink-0 cursor-pointer rounded-md bg-brand px-3 py-1.5 text-[12px] font-medium text-white hover:bg-brand-hover disabled:opacity-60";
}

export function secondaryButton(): string {
  return "shrink-0 cursor-pointer rounded-md border border-border px-3 py-1.5 text-[12px] font-medium text-foreground hover:bg-raised disabled:opacity-60";
}

// Renders the right "add a specific project/page/repo" UI for a connector and
// calls addSource, then onAdded(). Connected-only — callers gate on it.
export function AddSourceControls({
  connector,
  connected,
  accounts = [],
  existingRefs = [],
  onAdded,
}: {
  connector: Connector;
  connected: boolean;
  accounts?: IntegrationAccount[];
  existingRefs?: string[];
  onAdded: () => void;
}) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [gongscopeIds, setGongscopeIds] = useState("");

  async function add(body?: AddSourceBody) {
    setBusy(true);
    setError("");
    try {
      await addSource({
        source_type: connector.sourceType,
        ...body,
      });
      onAdded();
      return true;
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not add source");
      return false;
    } finally {
      setBusy(false);
    }
  }

  const errorRow = error ? (
    <div className="rounded-md bg-error/10 px-2 py-1.5 text-[11.5px] text-error">{error}</div>
  ) : null;

  if (connector.kind === "github") {
    return (
      <div className="space-y-2">
        <GitHubAccessControls
          busy={busy}
          onAddRepo={(repo) => add({ external_ref: repo.full_name, display_name: repo.full_name })}
          onChanged={onAdded}
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
        <DriveFolderControls
          busy={busy}
          onAddMyDrive={() => add({ external_ref: "root", display_name: "Google Drive" })}
          onAddFolder={(folderId, displayName) =>
            add({ external_ref: folderId, display_name: displayName })
          }
        />
        {errorRow}
      </div>
    );
  }

  if (connector.sourceType === "gong_calls") {
    const ids = gongscopeIds
      .split(",")
      .map((id) => id.trim())
      .filter(Boolean);
    return (
      <div className="space-y-2">
        {!connected && (
          <div className="text-[11.5px] text-muted-foreground">Connect Gong first to add it.</div>
        )}
        <input
          value={gongscopeIds}
          onChange={(event) => setGongscopeIds(event.target.value)}
          placeholder="Gong workspace IDs"
          className="w-full rounded-md border border-border bg-background px-2 py-1.5 text-[12px] text-foreground placeholder:text-muted-foreground"
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
          <div className="text-[11.5px] text-muted-foreground">Connect Gmail first to add a mailbox.</div>
        ) : (
          accounts.map((account) => {
            const label = account.account_email || account.account_display_name || account.account_key;
            const added = existingRefs.includes(account.account_key);
            return (
              <div key={account.account_key} className="flex items-center gap-3 rounded-lg border border-border px-3 py-2">
                <div className="min-w-0 flex-1">
                  <div className="truncate text-[13px] font-medium text-foreground">{label}</div>
                  <div className="text-[11.5px] text-muted-foreground">Mailbox</div>
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
          <div className="text-[11.5px] text-muted-foreground">Connect Slack first to add it.</div>
        )}
        {errorRow}
      </div>
    );
  }

  // kind "auto" — granola/gong. The backend resolves the ref.
  return (
    <div className="space-y-2">
      {!connected && (
        <div className="text-[11.5px] text-muted-foreground">Connect {connector.label} first to add it.</div>
      )}
      <button type="button" onClick={() => void add()} disabled={busy || !connected} className={secondaryButton()}>
        {busy ? "Adding..." : "Add"}
      </button>
      {errorRow}
    </div>
  );
}

// A Drive source syncs one folder subtree (external_ref is the folder id;
// "root" means all of My Drive). A pasted folder link reaches any folder the
// account can read — nested or shared — without a Drive-listing endpoint.
export function parseDriveFolderId(input: string): string | null {
  const trimmed = input.trim();
  const fromUrl = trimmed.match(/\/folders\/([A-Za-z0-9_-]+)/);
  if (fromUrl) return fromUrl[1];
  if (/^[A-Za-z0-9_-]{15,}$/.test(trimmed)) return trimmed;
  return null;
}

function DriveFolderControls({
  busy,
  onAddMyDrive,
  onAddFolder,
}: {
  busy: boolean;
  onAddMyDrive: () => Promise<boolean>;
  onAddFolder: (folderId: string, displayName: string) => Promise<boolean>;
}) {
  const [link, setLink] = useState("");
  const [name, setName] = useState("");
  const folderId = parseDriveFolderId(link);

  async function addFolder() {
    if (!folderId) return;
    const added = await onAddFolder(folderId, name.trim() || "Google Drive folder");
    if (added) {
      setLink("");
      setName("");
    }
  }

  return (
    <div className="space-y-2">
      <div className="flex items-center gap-2">
        <button type="button" onClick={() => void onAddMyDrive()} disabled={busy} className={secondaryButton()}>
          {busy ? "Adding..." : "Add My Drive"}
        </button>
        <span className="text-[11.5px] text-muted-foreground">or sync just one folder:</span>
      </div>
      <input
        value={link}
        onChange={(event) => setLink(event.target.value)}
        placeholder="Paste a Drive folder link"
        className="w-full rounded-md border border-border bg-background px-2 py-1.5 text-[12px] text-foreground placeholder:text-muted-foreground"
        disabled={busy}
      />
      <div className="flex items-center gap-2">
        <input
          value={name}
          onChange={(event) => setName(event.target.value)}
          placeholder="Name (e.g. Knowledge Base)"
          className="w-full rounded-md border border-border bg-background px-2 py-1.5 text-[12px] text-foreground placeholder:text-muted-foreground"
          disabled={busy}
        />
        <button type="button" onClick={() => void addFolder()} disabled={busy || !folderId} className={primaryButton()}>
          {busy ? "Adding..." : "Add folder"}
        </button>
      </div>
      {link.trim() !== "" && !folderId && (
        <div className="text-[11.5px] text-muted-foreground">
          That doesn&apos;t look like a folder link — expected drive.google.com/drive/folders/…
        </div>
      )}
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
              <span className="block truncate text-[11.5px] text-muted-foreground">
                {channel.is_private ? "Private" : "Channel"} · {channel.id}
              </span>
            </span>
          </label>
        ))}
      </PickerShell>
      <div className="mt-2 flex items-center justify-between gap-3">
        <div className="text-[11.5px] text-muted-foreground">{selectedIds.length} selected</div>
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

// The "Repository access" block: all-repos mode vs. hand-picked repos, in the
// style of GitHub's own App-install screen. Enabling all-repos registers a
// source per visible repo server-side and keeps the set current hourly;
// switching back to select stops auto-registration but keeps existing sources.
export function GitHubAccessControls({
  busy,
  onAddRepo,
  onChanged,
}: {
  busy: boolean;
  onAddRepo: (repo: GitHubRepoSummary) => Promise<boolean>;
  onChanged: () => void;
}) {
  const [view, setView] = useState<"all" | "select" | null>(null);
  const [enabled, setEnabled] = useState(false);
  const [repos, setRepos] = useState<GitHubRepoSummary[] | null>(null);
  const [syncResult, setSyncResult] = useState<GitHubRepoAccess | null>(null);
  const [busyAll, setBusyAll] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    let cancelled = false;
    getGitHubRepoAccess()
      .then((access) => {
        if (cancelled) return;
        setEnabled(access.all_repos);
        setView(access.all_repos ? "all" : "select");
      })
      .catch((e) => {
        if (!cancelled) setError(e instanceof Error ? e.message : "Could not load repo access");
      });
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

  async function chooseSelect() {
    setView("select");
    if (!enabled) return;
    setError("");
    try {
      await setGitHubRepoAccess(false);
      setEnabled(false);
      setSyncResult(null);
    } catch (e) {
      setView("all");
      setError(e instanceof Error ? e.message : "Could not update repo access");
    }
  }

  async function syncAll() {
    setBusyAll(true);
    setError("");
    try {
      const result = await setGitHubRepoAccess(true);
      setEnabled(true);
      setSyncResult(result);
      onChanged();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not sync repositories");
    } finally {
      setBusyAll(false);
    }
  }

  if (view === null && !error) {
    return <div className="py-2 text-[12px] text-muted">Loading…</div>;
  }

  const count = repos?.length ?? null;
  return (
    <div className="space-y-2">
      <div role="radiogroup" aria-label="Repository access" className="space-y-2">
        <AccessChoice
          checked={view === "all"}
          onClick={() => setView("all")}
          title={<>All repositories{count !== null && <span className="font-medium text-dim"> · {count}</span>}</>}
          description="Everything you can see — your own repos, collaborations, and org repos. Repos you gain access to later sync automatically."
        />
        <AccessChoice
          checked={view === "select"}
          onClick={() => void chooseSelect()}
          title="Only select repositories"
          description="Pick individual repos to sync. You can add more anytime."
        />
      </div>

      {view === "all" &&
        (enabled ? (
          <div className="flex items-center gap-2 rounded-md bg-surface px-3 py-2.5 text-[12.5px] text-dim">
            <span className="inline-block h-1.5 w-1.5 shrink-0 rounded-full bg-success" aria-hidden />
            <span>
              {syncResult?.created != null && `${syncResult.created} added · `}
              All repositories sync automatically — new repos you gain access to are added within
              an hour.
            </span>
          </div>
        ) : (
          <button type="button" disabled={busyAll} onClick={() => void syncAll()} className={primaryButton()}>
            {busyAll ? "Syncing..." : `Sync all${count !== null ? ` ${count}` : ""} repositories`}
          </button>
        ))}

      {view === "select" && <GitHubRepoPicker repos={repos} busy={busy} onAdd={onAddRepo} />}

      {error && (
        <div className="rounded-md bg-error/10 px-2 py-1.5 text-[11.5px] text-error">{error}</div>
      )}
    </div>
  );
}

function AccessChoice({
  checked,
  onClick,
  title,
  description,
}: {
  checked: boolean;
  onClick: () => void;
  title: ReactNode;
  description: string;
}) {
  return (
    <button
      type="button"
      role="radio"
      aria-checked={checked}
      onClick={onClick}
      className={
        "flex w-full cursor-pointer items-start gap-2.5 rounded-lg border p-3 text-left transition-colors " +
        (checked ? "border-brand bg-[var(--color-brand-50)]" : "border-border hover:bg-surface")
      }
    >
      <span
        aria-hidden
        className={
          "mt-0.5 grid h-[15px] w-[15px] shrink-0 place-items-center rounded-full border-[1.5px] " +
          (checked ? "border-brand" : "border-muted")
        }
      >
        {checked && <span className="h-[7px] w-[7px] rounded-full bg-brand" />}
      </span>
      <span className="min-w-0">
        <span className="block text-[13px] font-semibold text-foreground">{title}</span>
        <span className="mt-0.5 block text-[12px] text-dim">{description}</span>
      </span>
    </button>
  );
}

export function GitHubRepoPicker({
  repos,
  busy,
  onAdd,
}: {
  repos: GitHubRepoSummary[] | null;
  busy: boolean;
  onAdd: (repo: GitHubRepoSummary) => Promise<boolean>;
}) {
  const [query, setQuery] = useState("");

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
      error=""
      loading={repos === null}
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
          className="flex w-full cursor-pointer items-start gap-2 rounded-md px-2 py-1.5 text-left hover:bg-raised disabled:opacity-60"
        >
          <GitHubIcon className="mt-0.5 text-muted-foreground" size={14} />
          <span className="min-w-0 flex-1">
            <span className="block truncate text-[12.5px] font-medium text-foreground">
              {repo.full_name}
            </span>
            {repo.description && (
              <span className="block truncate text-[11.5px] text-muted-foreground">{repo.description}</span>
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
          className="flex w-full cursor-pointer items-start gap-2 rounded-md px-2 py-1.5 text-left hover:bg-raised disabled:opacity-60"
        >
          <NotionIcon className="mt-0.5 text-muted-foreground" size={14} />
          <span className="min-w-0 flex-1">
            <span className="block truncate text-[12.5px] font-medium text-foreground">
              {page.title || "Untitled"}
            </span>
            <span className="block truncate text-[11.5px] text-muted-foreground">{page.url}</span>
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
          className="flex w-full cursor-pointer items-start gap-2 rounded-md px-2 py-1.5 text-left hover:bg-raised disabled:opacity-60"
        >
          <JiraIcon className="mt-0.5" size={14} />
          <span className="min-w-0 flex-1">
            <span className="block truncate text-[12.5px] font-medium text-foreground">
              {project.name} <span className="text-muted-foreground">({project.key})</span>
            </span>
            <span className="block truncate text-[11.5px] text-muted-foreground">{project.site_name}</span>
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
          className="flex w-full cursor-pointer items-start gap-2 rounded-md px-2 py-1.5 text-left hover:bg-raised disabled:opacity-60"
        >
          <AsanaIcon className="mt-0.5" size={14} />
          <span className="min-w-0 flex-1">
            <span className="block truncate text-[12.5px] font-medium text-foreground">
              {project.name}
            </span>
            <span className="block truncate text-[11.5px] text-muted-foreground">{project.workspace_name}</span>
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
          <span className="mb-1 block text-[11.5px] text-muted-foreground">
            {field.label}
            {field.optional && <span className="ml-1 text-dim">(optional)</span>}
          </span>
          <input
            type={field.secret ? "password" : "text"}
            value={values[field.name] ?? ""}
            placeholder={field.placeholder}
            autoComplete="off"
            onChange={(e) => setValues((v) => ({ ...v, [field.name]: e.target.value }))}
            className="w-full rounded-md border border-border bg-surface px-2 py-1.5 text-[12px] text-foreground placeholder:text-muted-foreground focus:border-brand focus:outline-none"
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
        className="mb-2 w-full rounded-md border border-border bg-surface px-2 py-1.5 text-[12px] text-foreground placeholder:text-muted-foreground focus:border-brand focus:outline-none"
      />
      {error ? (
        <div className="rounded-md bg-error/10 px-2 py-1.5 text-[11.5px] text-error">{error}</div>
      ) : loading ? (
        <div className="px-2 py-3 text-[12px] text-muted-foreground">Loading...</div>
      ) : hasChildren ? (
        <div className="max-h-48 overflow-y-auto">{children}</div>
      ) : (
        <div className="px-2 py-3 text-[12px] text-muted-foreground">{empty}</div>
      )}
    </div>
  );
}
