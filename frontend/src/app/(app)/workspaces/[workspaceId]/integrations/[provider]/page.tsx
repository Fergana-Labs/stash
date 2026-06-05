"use client";

import { useParams, usePathname, useRouter, useSearchParams } from "next/navigation";
import Link from "next/link";
import { useCallback, useEffect, useState } from "react";

import { useBreadcrumbs } from "../../../../../../components/BreadcrumbContext";
import { useAuth } from "../../../../../../hooks/useAuth";
import {
  deleteWorkspaceSource,
  fetchSourceHistory,
  getSourceEntries,
  getSourceStatus,
  listWorkspaceSources,
  querySource,
  readSourceDoc,
  searchSource,
  syncWorkspaceSource,
  type SourceEntry,
  type SourceSearchHit,
  type WorkspaceSource,
} from "../../../../../../lib/api";
import {
  disconnectIntegration,
  listIntegrations,
  startConnect,
  submitCredentials,
  type IntegrationStatus,
} from "../../../../../../lib/integrations";
import { connectorForProvider, connectorIcon } from "../../../../../../components/integrations/connectors";
import {
  AddSourceControls,
  CredentialForm,
  primaryButton,
  secondaryButton,
} from "../../../../../../components/integrations/pickers";

// One-line "how it's indexed" descriptor per source type.
const INDEX_DESCRIPTOR: Record<string, string> = {
  github_repo: "Full repo copied + searchable",
  google_drive: "Indexed; searched live (Drive full-text)",
  notion: "Pages copied + full-text search",
  jira_project: "Searched live via Jira (federated)",
  asana_project: "Searched live via Asana (federated)",
  slack: "Messages copied + searchable",
  granola: "Meeting notes copied + searchable",
  gong_calls: "Call transcripts copied + searchable",
  snowflake: "Live read-only SQL",
};

export default function IntegrationPage() {
  const params = useParams();
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const workspaceId = params.workspaceId as string;
  const provider = params.provider as string;
  const highlightSourceId = searchParams.get("source");
  const { user, loading } = useAuth();

  const connector = connectorForProvider(provider);

  const [status, setStatus] = useState<IntegrationStatus | null>(null);
  const [sources, setSources] = useState<WorkspaceSource[]>([]);
  const [openSourceId, setOpenSourceId] = useState<string | null>(highlightSourceId);
  const [showCreds, setShowCreds] = useState(false);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState("");

  useBreadcrumbs(
    [{ label: connector?.label ?? "Integration" }],
    `${workspaceId}/integrations/${provider}`,
  );

  const refresh = useCallback(async () => {
    if (!connector) return;
    setError("");
    const [integrations, allSources] = await Promise.all([
      listIntegrations(),
      listWorkspaceSources(workspaceId),
    ]);
    setStatus(integrations.providers.find((p) => p.provider === provider) ?? null);
    setSources(allSources.filter((s) => s.type === connector.sourceType));
  }, [connector, provider, workspaceId]);

  useEffect(() => {
    if (!user) return;
    refresh().catch((e) => setError(e instanceof Error ? e.message : "Could not load integration"));
  }, [user, refresh]);

  useEffect(() => {
    if (!loading && !user) router.push("/login");
  }, [user, loading, router]);

  if (loading) return null;
  if (!user) return null;

  if (!connector) {
    return (
      <div className="scroll-thin flex-1 overflow-y-auto">
        <div className="mx-auto max-w-3xl px-12 py-8">
          <h1 className="font-display text-[20px] font-semibold text-foreground">Unknown integration</h1>
          <p className="mt-2 text-[13px] text-muted">
            No integration matches “{provider}”.{" "}
            <Link href="/settings" className="text-brand hover:underline">
              Manage in Settings
            </Link>
            .
          </p>
        </div>
      </div>
    );
  }

  const connected = !!status?.connected;
  const account = status?.account_email || status?.account_display_name;

  async function connect() {
    setBusy("connect");
    setError("");
    try {
      await startConnect(connector!.provider, pathname);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not start connection");
      setBusy(null);
    }
  }

  async function submitCreds(values: Record<string, string>) {
    setBusy("connect");
    setError("");
    try {
      await submitCredentials(connector!.provider, values);
      setShowCreds(false);
      await refresh();
      return true;
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not connect");
      return false;
    } finally {
      setBusy(null);
    }
  }

  async function disconnect() {
    if (!confirm(`Disconnect ${connector!.label}? You'll need to reconnect to sync its sources again.`)) {
      return;
    }
    setBusy("disconnect");
    setError("");
    try {
      await disconnectIntegration(connector!.provider);
      await refresh();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not disconnect");
    } finally {
      setBusy(null);
    }
  }

  async function syncSource(source: WorkspaceSource) {
    setBusy(`sync:${source.source}`);
    setError("");
    try {
      await syncWorkspaceSource(workspaceId, source.source);
      await refresh();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not start sync");
    } finally {
      setBusy(null);
    }
  }

  async function removeSource(source: WorkspaceSource) {
    if (!confirm(`Remove ${source.display_name}?`)) return;
    setBusy(`delete:${source.source}`);
    setError("");
    try {
      await deleteWorkspaceSource(workspaceId, source.source);
      if (openSourceId === source.source) setOpenSourceId(null);
      await refresh();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not remove source");
    } finally {
      setBusy(null);
    }
  }

  const openSource = sources.find((s) => s.source === openSourceId) ?? null;

  return (
    <div className="scroll-thin flex-1 overflow-y-auto">
      <div className="mx-auto max-w-3xl px-12 py-8">
        {/* Header */}
        <div className="flex items-center gap-3">
          <span className="flex h-7 w-7 shrink-0 items-center justify-center">
            {connectorIcon(connector.provider)}
          </span>
          <div className="min-w-0 flex-1">
            <h1 className="font-display text-[20px] font-semibold text-foreground">{connector.label}</h1>
            <div className="text-[12.5px] text-muted">
              {connected && account ? `Connected as ${account}` : connector.blurb}
            </div>
          </div>
          <Link href="/settings" className="shrink-0 text-[12px] text-muted hover:text-foreground hover:underline">
            Manage in Settings
          </Link>
        </div>

        <div className="mt-3 flex items-center gap-2">
          {!connected && status?.auth_kind === "api_key" ? (
            <button
              type="button"
              onClick={() => setShowCreds((v) => !v)}
              disabled={busy === "connect"}
              className={primaryButton()}
            >
              {showCreds ? "Cancel" : "Connect"}
            </button>
          ) : !connected ? (
            <button type="button" onClick={() => void connect()} disabled={busy === "connect"} className={primaryButton()}>
              {busy === "connect" ? "Connecting..." : "Connect"}
            </button>
          ) : (
            <button
              type="button"
              onClick={() => void disconnect()}
              disabled={busy === "disconnect"}
              className="shrink-0 rounded-md border border-border px-3 py-1.5 text-[12px] font-medium text-muted hover:border-error/40 hover:text-error disabled:opacity-60"
            >
              {busy === "disconnect" ? "Disconnecting..." : "Disconnect"}
            </button>
          )}
        </div>

        {showCreds && !connected && status?.auth_kind === "api_key" && status.credential_fields && (
          <CredentialForm
            fields={status.credential_fields}
            busy={busy === "connect"}
            onSubmit={submitCreds}
          />
        )}

        {error && (
          <div className="mt-4 rounded-md border border-error/30 bg-error/10 px-3 py-2 text-[12px] text-error">
            {error}
          </div>
        )}

        {/* Add */}
        {connected && (
          <section className="mt-6">
            <h2 className="mb-2 text-[11px] font-semibold uppercase tracking-wide text-muted">Add</h2>
            <div className="rounded-lg border border-border bg-surface px-3 py-3">
              <AddSourceControls
                connector={connector}
                workspaceId={workspaceId}
                connected={connected}
                onAdded={() => void refresh()}
              />
            </div>
          </section>
        )}

        {/* Added sources */}
        <section className="mt-6">
          <h2 className="mb-2 text-[11px] font-semibold uppercase tracking-wide text-muted">Added sources</h2>
          {sources.length === 0 ? (
            <div className="rounded-lg border border-dashed border-border bg-surface/30 px-4 py-6 text-center text-[12.5px] text-muted">
              {connected ? "Nothing added yet." : "Connect to add sources."}
            </div>
          ) : (
            <div className="space-y-2">
              {sources.map((source) => (
                <SourceRow
                  key={source.source}
                  workspaceId={workspaceId}
                  source={source}
                  highlighted={source.source === highlightSourceId}
                  open={source.source === openSourceId}
                  busySync={busy === `sync:${source.source}`}
                  busyDelete={busy === `delete:${source.source}`}
                  onOpen={() => setOpenSourceId((v) => (v === source.source ? null : source.source))}
                  onSync={() => void syncSource(source)}
                  onRemove={() => void removeSource(source)}
                />
              ))}
            </div>
          )}
        </section>

        {/* Browse */}
        {openSource && (
          <section className="mt-6">
            <h2 className="mb-2 text-[11px] font-semibold uppercase tracking-wide text-muted">
              Browse · {openSource.display_name}
            </h2>
            <BrowsePanel workspaceId={workspaceId} source={openSource} onRefresh={() => void refresh()} />
          </section>
        )}
      </div>
    </div>
  );
}

function relativeTime(iso: string | null | undefined): string {
  if (!iso) return "never synced";
  const then = new Date(iso).getTime();
  if (Number.isNaN(then)) return "never synced";
  const diffMin = Math.round((Date.now() - then) / 60000);
  if (diffMin < 1) return "synced just now";
  if (diffMin < 60) return `synced ${diffMin}m ago`;
  const diffH = Math.round(diffMin / 60);
  if (diffH < 24) return `synced ${diffH}h ago`;
  const diffD = Math.round(diffH / 24);
  if (diffD < 7) return `synced ${diffD}d ago`;
  return `synced ${new Date(iso).toLocaleDateString()}`;
}

function SyncPill({ syncStatus }: { syncStatus: string | null | undefined }) {
  const s = syncStatus ?? "idle";
  const cls =
    s === "syncing"
      ? "border-blue-300/50 bg-blue-500/10 text-blue-600"
      : s === "failed"
      ? "border-error/40 bg-error/10 text-error"
      : "border-border bg-base text-muted";
  return (
    <span className={"inline-flex items-center rounded-full border px-2 py-0.5 text-[10.5px] font-medium " + cls}>
      {s}
    </span>
  );
}

function SourceRow({
  workspaceId,
  source,
  highlighted,
  open,
  busySync,
  busyDelete,
  onOpen,
  onSync,
  onRemove,
}: {
  workspaceId: string;
  source: WorkspaceSource;
  highlighted: boolean;
  open: boolean;
  busySync: boolean;
  busyDelete: boolean;
  onOpen: () => void;
  onSync: () => void;
  onRemove: () => void;
}) {
  const [itemCount, setItemCount] = useState<number | null>(null);

  useEffect(() => {
    let cancelled = false;
    getSourceStatus(workspaceId, source.source)
      .then((s) => {
        if (!cancelled) setItemCount(s.item_count);
      })
      .catch(() => {});
    return () => {
      cancelled = true;
    };
  }, [workspaceId, source.source]);

  return (
    <div
      className={
        "rounded-lg border bg-surface px-3 py-2.5 " +
        (highlighted ? "border-brand/50 ring-1 ring-brand/30" : "border-border")
      }
    >
      <div className="flex items-center gap-3">
        <button type="button" onClick={onOpen} className="min-w-0 flex-1 text-left">
          <div className="truncate text-[13.5px] font-medium text-foreground">{source.display_name}</div>
          <div className="mt-1 flex flex-wrap items-center gap-2 text-[11.5px] text-muted">
            <SyncPill syncStatus={source.sync_status} />
            <span>{relativeTime(source.last_synced_at)}</span>
            {itemCount !== null && <span>· {itemCount} items</span>}
            <span>· {INDEX_DESCRIPTOR[source.type] ?? source.type}</span>
          </div>
          {source.sync_error && (
            <div className="mt-1 truncate text-[11px] text-error">{source.sync_error}</div>
          )}
        </button>
        <div className="flex shrink-0 items-center gap-2">
          <button
            type="button"
            onClick={onOpen}
            className="rounded-md border border-border px-2 py-1 text-[11.5px] text-muted hover:text-foreground"
          >
            {open ? "Close" : "Browse"}
          </button>
          <button
            type="button"
            disabled={busySync}
            onClick={onSync}
            className="rounded-md border border-border px-2 py-1 text-[11.5px] text-muted hover:text-foreground disabled:opacity-60"
          >
            {busySync ? "Syncing..." : "Sync"}
          </button>
          <button
            type="button"
            disabled={busyDelete}
            onClick={onRemove}
            className="rounded-md border border-border px-2 py-1 text-[11.5px] text-muted hover:text-error disabled:opacity-60"
          >
            Remove
          </button>
        </div>
      </div>
    </div>
  );
}

function BrowsePanel({
  workspaceId,
  source,
  onRefresh,
}: {
  workspaceId: string;
  source: WorkspaceSource;
  onRefresh: () => void;
}) {
  if (source.capability === "queryable") {
    return <QueryablePanel workspaceId={workspaceId} source={source} />;
  }
  if (source.capability === "searchable") {
    return <SearchablePanel workspaceId={workspaceId} source={source} onRefresh={onRefresh} />;
  }
  return <NavigablePanel workspaceId={workspaceId} source={source} onRefresh={onRefresh} />;
}

// Shows the full content of one document/entry inside a browse panel.
function DocViewer({
  workspaceId,
  source,
  refValue,
  name,
  onClose,
}: {
  workspaceId: string;
  source: string;
  refValue: string;
  name?: string;
  onClose: () => void;
}) {
  const [content, setContent] = useState<string | null>(null);
  const [title, setTitle] = useState(name ?? "");
  const [error, setError] = useState("");

  useEffect(() => {
    let cancelled = false;
    setContent(null);
    setError("");
    readSourceDoc(workspaceId, source, refValue)
      .then((doc) => {
        if (cancelled) return;
        setContent(doc.content ?? "");
        if (doc.name) setTitle(doc.name);
      })
      .catch((e) => {
        if (!cancelled) setError(e instanceof Error ? e.message : "Could not read document");
      });
    return () => {
      cancelled = true;
    };
  }, [workspaceId, source, refValue]);

  return (
    <div className="mt-3 rounded-lg border border-border bg-base p-3">
      <div className="mb-2 flex items-center justify-between gap-2">
        <div className="min-w-0 truncate text-[12.5px] font-medium text-foreground">{title || refValue}</div>
        <button type="button" onClick={onClose} className="shrink-0 text-[12px] text-muted hover:text-foreground">
          Close
        </button>
      </div>
      {error ? (
        <div className="text-[12px] text-error">{error}</div>
      ) : content === null ? (
        <div className="text-[12px] text-muted">Loading…</div>
      ) : (
        <pre className="scroll-thin max-h-96 overflow-auto whitespace-pre-wrap break-words text-[12px] text-foreground">
          {content}
        </pre>
      )}
    </div>
  );
}

function QueryablePanel({ workspaceId, source }: { workspaceId: string; source: WorkspaceSource }) {
  const [tables, setTables] = useState<SourceEntry[] | null>(null);
  const [sql, setSql] = useState("");
  const [result, setResult] = useState<{ columns?: string[]; rows?: unknown[][]; error?: string } | null>(null);
  const [running, setRunning] = useState(false);

  useEffect(() => {
    let cancelled = false;
    getSourceEntries(workspaceId, source.source)
      .then((entries) => {
        if (!cancelled) setTables(entries);
      })
      .catch(() => {
        if (!cancelled) setTables([]);
      });
    return () => {
      cancelled = true;
    };
  }, [workspaceId, source.source]);

  async function run() {
    if (!sql.trim()) return;
    setRunning(true);
    try {
      setResult(await querySource(workspaceId, source.source, sql));
    } catch (e) {
      setResult({ error: e instanceof Error ? e.message : "Query failed" });
    } finally {
      setRunning(false);
    }
  }

  return (
    <div className="rounded-lg border border-border bg-surface p-3">
      <div className="mb-2 text-[11px] font-semibold uppercase tracking-wide text-muted">Tables</div>
      {tables === null ? (
        <div className="text-[12px] text-muted">Loading…</div>
      ) : tables.length === 0 ? (
        <div className="text-[12px] text-muted">No tables found.</div>
      ) : (
        <div className="flex flex-wrap gap-1.5">
          {tables.map((t) => (
            <button
              key={t.name}
              type="button"
              onClick={() => setSql(`SELECT * FROM ${t.name} LIMIT 100`)}
              className="rounded-md border border-border bg-base px-2 py-1 text-[11.5px] text-foreground hover:bg-raised"
            >
              {t.name}
            </button>
          ))}
        </div>
      )}

      <textarea
        value={sql}
        onChange={(e) => setSql(e.target.value)}
        placeholder="SELECT * FROM ... LIMIT 100"
        rows={4}
        className="mt-3 w-full rounded-md border border-border bg-base px-2 py-1.5 font-mono text-[12px] text-foreground placeholder:text-muted focus:border-brand focus:outline-none"
      />
      <button type="button" onClick={() => void run()} disabled={running || !sql.trim()} className={primaryButton() + " mt-2"}>
        {running ? "Running..." : "Run"}
      </button>

      {result?.error && (
        <div className="mt-3 rounded-md border border-error/30 bg-error/10 px-3 py-2 text-[12px] text-error">
          {result.error}
        </div>
      )}
      {result && !result.error && result.columns && (
        <div className="scroll-thin mt-3 overflow-auto rounded-md border border-border">
          <table className="w-full text-left text-[12px]">
            <thead className="bg-base/70">
              <tr>
                {result.columns.map((col) => (
                  <th key={col} className="whitespace-nowrap px-2 py-1.5 font-medium text-muted">
                    {col}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {(result.rows ?? []).map((row, i) => (
                <tr key={i} className="border-t border-border">
                  {row.map((cell, j) => (
                    <td key={j} className="whitespace-nowrap px-2 py-1.5 text-foreground">
                      {cell === null ? "" : String(cell)}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

function SearchablePanel({
  workspaceId,
  source,
  onRefresh,
}: {
  workspaceId: string;
  source: WorkspaceSource;
  onRefresh: () => void;
}) {
  const [query, setQuery] = useState("");
  const [hits, setHits] = useState<SourceSearchHit[] | null>(null);
  const [recent, setRecent] = useState<SourceEntry[] | null>(null);
  const [searching, setSearching] = useState(false);
  const [openDoc, setOpenDoc] = useState<{ ref: string; name?: string } | null>(null);

  const showHistory = source.type === "slack" || source.type === "gong_calls";

  useEffect(() => {
    let cancelled = false;
    getSourceEntries(workspaceId, source.source)
      .then((entries) => {
        if (!cancelled) setRecent(entries);
      })
      .catch(() => {
        if (!cancelled) setRecent([]);
      });
    return () => {
      cancelled = true;
    };
  }, [workspaceId, source.source]);

  async function search() {
    if (!query.trim()) return;
    setSearching(true);
    try {
      setHits(await searchSource(workspaceId, query, source.source));
    } catch {
      setHits([]);
    } finally {
      setSearching(false);
    }
  }

  return (
    <div className="rounded-lg border border-border bg-surface p-3">
      <form
        onSubmit={(e) => {
          e.preventDefault();
          void search();
        }}
        className="flex gap-2"
      >
        <input
          type="search"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder={`Search ${source.display_name}...`}
          className="flex-1 rounded-md border border-border bg-base px-2 py-1.5 text-[12px] text-foreground placeholder:text-muted focus:border-brand focus:outline-none"
        />
        <button type="submit" disabled={searching || !query.trim()} className={primaryButton()}>
          {searching ? "Searching..." : "Search"}
        </button>
      </form>

      {hits !== null && (
        <div className="mt-3">
          <div className="mb-1 text-[11px] font-semibold uppercase tracking-wide text-muted">Results</div>
          {hits.length === 0 ? (
            <div className="text-[12px] text-muted">No matches.</div>
          ) : (
            <div className="space-y-1">
              {hits.map((hit) => (
                <button
                  key={hit.ref}
                  type="button"
                  onClick={() => setOpenDoc({ ref: hit.ref, name: hit.name })}
                  className="block w-full rounded-md px-2 py-1.5 text-left hover:bg-raised"
                >
                  <div className="truncate text-[12.5px] font-medium text-foreground">{hit.name || hit.ref}</div>
                  {hit.snippet && <div className="truncate text-[11.5px] text-muted">{hit.snippet}</div>}
                </button>
              ))}
            </div>
          )}
        </div>
      )}

      {recent && recent.length > 0 && (
        <div className="mt-3">
          <div className="mb-1 text-[11px] font-semibold uppercase tracking-wide text-muted">Recent</div>
          <div className="space-y-1">
            {recent.map((entry) => {
              const ref = entry.id ?? entry.path ?? entry.name;
              return (
                <button
                  key={ref}
                  type="button"
                  onClick={() => setOpenDoc({ ref, name: entry.name })}
                  className="block w-full truncate rounded-md px-2 py-1.5 text-left text-[12.5px] text-foreground hover:bg-raised"
                >
                  {entry.name}
                </button>
              );
            })}
          </div>
        </div>
      )}

      {openDoc && (
        <DocViewer
          workspaceId={workspaceId}
          source={source.source}
          refValue={openDoc.ref}
          name={openDoc.name}
          onClose={() => setOpenDoc(null)}
        />
      )}

      {showHistory && (
        <HistoryControl workspaceId={workspaceId} source={source} onFetched={onRefresh} />
      )}
    </div>
  );
}

function NavigablePanel({
  workspaceId,
  source,
  onRefresh,
}: {
  workspaceId: string;
  source: WorkspaceSource;
  onRefresh: () => void;
}) {
  const [path, setPath] = useState("");
  const [entries, setEntries] = useState<SourceEntry[] | null>(null);
  const [crumbs, setCrumbs] = useState<{ label: string; path: string }[]>([{ label: source.display_name, path: "" }]);
  const [openDoc, setOpenDoc] = useState<{ ref: string; name?: string } | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    let cancelled = false;
    setEntries(null);
    setError("");
    getSourceEntries(workspaceId, source.source, path)
      .then((next) => {
        if (!cancelled) setEntries(next);
      })
      .catch((e) => {
        if (!cancelled) {
          setEntries([]);
          setError(e instanceof Error ? e.message : "Could not list entries");
        }
      });
    return () => {
      cancelled = true;
    };
  }, [workspaceId, source.source, path]);

  // Folder-like entries (have a `path` and are a container) drill in; leaves open a doc.
  function isFolder(entry: SourceEntry): boolean {
    return entry.kind === "dir" || entry.kind === "folder" || entry.kind === "prefix" || entry.kind === "tree";
  }

  function openEntry(entry: SourceEntry) {
    if (isFolder(entry) && entry.path !== undefined) {
      setPath(entry.path);
      setCrumbs((c) => [...c, { label: entry.name, path: entry.path ?? "" }]);
      setOpenDoc(null);
      return;
    }
    const ref = entry.id ?? entry.path ?? entry.name;
    setOpenDoc({ ref, name: entry.name });
  }

  function goCrumb(index: number) {
    const target = crumbs[index];
    setPath(target.path);
    setCrumbs(crumbs.slice(0, index + 1));
    setOpenDoc(null);
  }

  return (
    <div className="rounded-lg border border-border bg-surface p-3">
      <div className="mb-2 flex flex-wrap items-center gap-1 text-[12px] text-muted">
        {crumbs.map((c, i) => (
          <span key={c.path + i} className="flex items-center gap-1">
            {i > 0 && <span className="text-muted/60">/</span>}
            <button
              type="button"
              onClick={() => goCrumb(i)}
              className={i === crumbs.length - 1 ? "text-foreground" : "hover:text-foreground hover:underline"}
            >
              {c.label}
            </button>
          </span>
        ))}
      </div>

      {error && <div className="mb-2 text-[12px] text-error">{error}</div>}

      {entries === null ? (
        <div className="text-[12px] text-muted">Loading…</div>
      ) : entries.length === 0 ? (
        <div className="text-[12px] text-muted">Empty.</div>
      ) : (
        <div className="space-y-0.5">
          {entries.map((entry) => {
            const key = entry.id ?? entry.path ?? entry.name;
            const folder = isFolder(entry);
            return (
              <button
                key={key}
                type="button"
                onClick={() => openEntry(entry)}
                className="flex w-full items-center gap-2 rounded-md px-2 py-1.5 text-left hover:bg-raised"
              >
                <span aria-hidden className="text-[13px]">
                  {folder ? "📁" : "📄"}
                </span>
                <span className="min-w-0 flex-1 truncate text-[12.5px] text-foreground">{entry.name}</span>
              </button>
            );
          })}
        </div>
      )}

      {openDoc && (
        <DocViewer
          workspaceId={workspaceId}
          source={source.source}
          refValue={openDoc.ref}
          name={openDoc.name}
          onClose={() => setOpenDoc(null)}
        />
      )}

      {source.type === "slack" || source.type === "gong_calls" ? (
        <HistoryControl workspaceId={workspaceId} source={source} onFetched={onRefresh} />
      ) : null}
    </div>
  );
}

function HistoryControl({
  workspaceId,
  source,
  onFetched,
}: {
  workspaceId: string;
  source: WorkspaceSource;
  onFetched: () => void;
}) {
  const [since, setSince] = useState("");
  const [until, setUntil] = useState("");
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");

  async function run() {
    if (!since) return;
    setBusy(true);
    setMessage("");
    try {
      const result = await fetchSourceHistory(workspaceId, source.source, since, until || undefined);
      setMessage(`Fetched ${result.fetched}`);
      onFetched();
    } catch (e) {
      setMessage(e instanceof Error ? e.message : "Could not fetch history");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="mt-3 rounded-md border border-border bg-base p-2.5">
      <div className="mb-2 text-[11px] font-semibold uppercase tracking-wide text-muted">Fetch older history</div>
      <div className="flex flex-wrap items-center gap-2">
        <label className="text-[11.5px] text-muted">
          Since
          <input
            type="date"
            value={since}
            onChange={(e) => setSince(e.target.value)}
            className="ml-1 rounded-md border border-border bg-surface px-2 py-1 text-[12px] text-foreground focus:border-brand focus:outline-none"
          />
        </label>
        <label className="text-[11.5px] text-muted">
          Until
          <input
            type="date"
            value={until}
            onChange={(e) => setUntil(e.target.value)}
            className="ml-1 rounded-md border border-border bg-surface px-2 py-1 text-[12px] text-foreground focus:border-brand focus:outline-none"
          />
        </label>
        <button type="button" onClick={() => void run()} disabled={busy || !since} className={secondaryButton()}>
          {busy ? "Fetching..." : "Fetch"}
        </button>
        {message && <span className="text-[11.5px] text-muted">{message}</span>}
      </div>
    </div>
  );
}
