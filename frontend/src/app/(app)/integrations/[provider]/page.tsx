"use client";

import { useParams, usePathname, useRouter, useSearchParams } from "next/navigation";
import Link from "next/link";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { MoreHorizontal } from "lucide-react";

import { useBreadcrumbs } from "@/components/BreadcrumbContext";
import { useConfirm } from "@/components/ConfirmDialog";
import { useAuth } from "@/hooks/useAuth";
import {
  ApiError,
  deleteSource,
  fetchSourceHistory,
  getSourceEntries,
  getSourceStatus,
  listSources,
  readSourceDoc,
  searchSource,
  syncSource as syncSourceApi,
  type Source,
  type SourceEntry,
  type SourceSearchHit,
  type SourceStatus,
} from "@/lib/api";
import {
  disconnectIntegration,
  listIntegrations,
  startConnect,
  submitCredentials,
  type IntegrationStatus,
} from "@/lib/integrations";
import { connectorForProvider, connectorIcon, providerForSourceType } from "@/components/integrations/connectors";
import {
  AddSourceControls,
  CredentialForm,
  primaryButton,
  secondaryButton,
} from "@/components/integrations/pickers";
import PaywallModal from "@/components/PaywallModal";
import { ResourceShareDialog } from "@/components/share/ResourceShareButton";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import type { User } from "@/lib/types";

// How often a row re-checks a source that is mid-sync, and how many times before
// it gives up. A sync that hasn't settled in ~5 minutes is wedged; polling it for
// as long as the tab happens to be open buys nothing.
const SYNC_POLL_INTERVAL_MS = 3000;
const SYNC_POLL_MAX_ATTEMPTS = 100;

export default function IntegrationRoute() {
  const params = useParams();
  return <IntegrationDetail provider={params.provider as string} />;
}

// The integration manager for one provider. Rendered both as the
// /integrations/[provider] route and inside a workbench "tool" tab (clicking
// a connector in the Tools sidebar), so the provider comes in as a prop.
export function IntegrationDetail({ provider }: { provider: string }) {
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const highlightSourceId = searchParams.get("source");
  const { user, loading } = useAuth();
  const confirm = useConfirm();

  const connector = connectorForProvider(provider);

  const [status, setStatus] = useState<IntegrationStatus | null>(null);
  const [sources, setSources] = useState<Source[]>([]);
  const [openSourceId, setOpenSourceId] = useState<string | null>(highlightSourceId);
  const [showCreds, setShowCreds] = useState(false);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState("");
  const [paymentRequired, setPaymentRequired] = useState(false);

  useBreadcrumbs(
    [{ label: connector?.label ?? "Integration" }],
    `integrations/${provider}`,
  );

  const refresh = useCallback(async () => {
    if (!connector) return;
    setError("");
    const [integrations, allSources] = await Promise.all([
      listIntegrations(),
      listSources(),
    ]);
    setStatus(integrations.providers.find((p) => p.provider === provider) ?? null);
    // A provider can own more than one source type — a whole Drive and a
    // picked folder are different types on the same Google connector.
    setSources(allSources.filter((s) => providerForSourceType[s.type] === connector.provider));
  }, [connector, provider]);

  useEffect(() => {
    if (!user) return;
    refresh().catch((e) => setError(e instanceof Error ? e.message : "Could not load integration"));
  }, [user, refresh]);

  useEffect(() => {
    if (!loading && !user) router.push("/login");
  }, [user, loading, router]);

  useEffect(() => {
    // X auto-creates one source; open it straight into browse so the page
    // reads as "connected + your saves", not a source picker.
    if (connector?.singleSource && sources.length === 1 && !openSourceId) {
      setOpenSourceId(sources[0].source);
    }
  }, [connector, sources, openSourceId]);

  if (loading) return null;
  if (!user) return null;

  if (!connector) {
    return (
      <div className="scroll-thin flex-1 overflow-y-auto">
        <div className="mx-auto max-w-3xl px-12 py-8">
          <h1 className="font-display text-[20px] font-semibold text-foreground">Unknown integration</h1>
          <p className="mt-2 text-[13px] text-muted-foreground">
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

  // Extension-fed connectors (X, Instagram) have no OAuth integration — they're
  // "connected" once the browser extension has pushed at least one source.
  const isExtension = connector.kind === "extension";
  const singleSource = !!connector.singleSource;
  const connected = isExtension ? sources.length > 0 : !!status?.connected;
  const account = connectedAccountLabel(status);
  const canConnectAnother = connected && connector.provider === "gmail" && status?.auth_kind !== "api_key";
  const staleAccounts = status?.accounts.filter((a) => a.needs_reconnect) ?? [];

  async function connect() {
    setBusy("connect");
    setError("");
    try {
      await startConnect(connector!.provider, pathname);
    } catch (e) {
      if (e instanceof ApiError && e.status === 402) {
        setPaymentRequired(true);
      } else {
        setError(e instanceof Error ? e.message : "Could not start connection");
      }
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

  async function disconnect() {
    const ok = await confirm({
      title: `Disconnect ${connector!.label}?`,
      body: "You'll need to reconnect to sync its sources again.",
      confirmLabel: "Disconnect",
    });
    if (!ok) return;
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

  async function syncSource(source: Source) {
    setBusy(`sync:${source.source}`);
    setError("");
    try {
      await syncSourceApi(source.source);
      await refresh();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not start sync");
    } finally {
      setBusy(null);
    }
  }

  async function removeSource(source: Source) {
    const ok = await confirm({
      title: `Remove ${source.display_name}?`,
      confirmLabel: "Remove",
    });
    if (!ok) return;
    setBusy(`delete:${source.source}`);
    setError("");
    try {
      await deleteSource(source.source);
      if (openSourceId === source.source) setOpenSourceId(null);
      await refresh();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not remove source");
    } finally {
      setBusy(null);
    }
  }

  const openSource = sources.find((s) => s.source === openSourceId) ?? null;
  // The mock's uppercase "ADD A <thing>" / "<things>" labels read off the
  // connector's noun (Project / Repo / Page / …) — derived from the blurb fallback.
  const itemNoun = ITEM_NOUN[connector.sourceType] ?? "source";

  return (
    <div className="scroll-thin flex-1 overflow-y-auto">
      <div className="mx-auto max-w-3xl px-12 py-9">
        {/* Header: icon + label, connected account + quiet Disconnect top-right. */}
        <div className="flex items-center gap-3">
          <span className="grid h-[30px] w-[30px] shrink-0 place-items-center rounded-lg bg-[var(--color-brand-50)] text-[16px]">
            {connectorIcon(connector.provider)}
          </span>
          <h1 className="font-display text-[19px] font-semibold tracking-tight text-foreground">
            {connector.label}
          </h1>
          <div className="ml-auto flex items-center gap-3.5">
            {connected && account && (
              <span className="text-[12.5px] text-muted-foreground">
                {account}
              </span>
            )}
            {isExtension ? (
              <span className="text-[12.5px] text-muted-foreground">
                {connected ? "Synced from the browser extension" : "Save items with the browser extension"}
              </span>
            ) : connected ? (
              <>
                {canConnectAnother && (
                  <button type="button" onClick={() => void connect()} disabled={busy === "connect"} className={secondaryButton()}>
                    {busy === "connect" ? "Connecting..." : "Connect another"}
                  </button>
                )}
                <button
                  type="button"
                  onClick={() => void disconnect()}
                  disabled={busy === "disconnect"}
                  className="cursor-pointer rounded-lg px-3 py-1.5 text-[12px] font-semibold text-muted-foreground hover:bg-raised hover:text-foreground disabled:opacity-60"
                >
                  {busy === "disconnect"
                    ? "Disconnecting..."
                    : connector.provider === "gmail" && (status?.accounts.length ?? 0) > 1
                    ? "Disconnect all"
                    : "Disconnect"}
                </button>
              </>
            ) : status?.auth_kind === "api_key" ? (
              <button
                type="button"
                onClick={() => setShowCreds((v) => !v)}
                disabled={busy === "connect"}
                className={primaryButton()}
              >
                {showCreds ? "Cancel" : "Connect"}
              </button>
            ) : (
              <button type="button" onClick={() => void connect()} disabled={busy === "connect"} className={primaryButton()}>
                {busy === "connect" ? "Connecting..." : "Connect"}
              </button>
            )}
          </div>
        </div>

        {/* Subtitle: what this integration does + a quiet Settings link. */}
        <div className="mb-6 ml-[42px] mt-0.5 text-[12.5px] text-muted-foreground">
          {connector.blurb}{" "}·{" "}
          <Link href="/settings" className="font-semibold text-brand hover:underline">
            Manage in Settings
          </Link>
        </div>

        {staleAccounts.length > 0 && (
          <div className="mt-4 flex items-center justify-between gap-3 rounded-md border border-error/30 bg-error/10 px-3 py-2 text-[12px] text-error">
            <span>
              {staleAccounts.length === 1
                ? `${staleAccounts[0].account_email ?? staleAccounts[0].account_key} is connected but its access expired — search returns nothing until you reconnect.`
                : `${staleAccounts.length} accounts are connected but their access expired — search returns nothing until you reconnect.`}
            </span>
            <button type="button" onClick={() => void connect()} disabled={busy === "connect"} className={secondaryButton()}>
              {busy === "connect" ? "Connecting..." : "Reconnect"}
            </button>
          </div>
        )}

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

        {paymentRequired && <PaywallModal onClose={() => setPaymentRequired(false)} />}

        {/* Add a <thing> (for GitHub: the all-vs-select repository access chooser).
            Extension-fed and single-source connectors (X) have nothing to add by
            hand — their one source is created on connect. */}
        {connected && !isExtension && !singleSource && (
          <section className="mt-6">
            <SectionLabel>
              {connector.kind === "github" ? "Repository access" : `Add a ${itemNoun}`}
            </SectionLabel>
            <AddSourceControls
              connector={connector}
              connected={connected}
              accounts={status?.accounts ?? []}
              existingRefs={sources.map((source) => source.external_ref).filter((ref): ref is string => Boolean(ref))}
              onAdded={() => void refresh()}
            />
          </section>
        )}

        {/* <Things>. Single-source connectors (X) skip the "Sources" heading —
            there's just the one, shown as the connection's sync status. */}
        <section className="mt-7">
          {!singleSource && (
            <SectionLabel>{itemNoun === "source" ? "Sources" : `${capitalize(itemNoun)}s`}</SectionLabel>
          )}
          {sources.length === 0 ? (
            <div className="py-3 text-[12.5px] text-muted-foreground">
              {isExtension
                ? `Install the Stash browser extension and save on ${connector.label} — your items will appear here.`
                : connected
                  ? "Nothing added yet."
                  : "Connect to add sources."}
            </div>
          ) : (
            <div>
              {sources.map((source) => (
                <SourceRow
                  key={source.source}
                  source={source}
                  currentUser={user}
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

        {/* Browse · <name> */}
        {openSource && (
          <section className="mt-7">
            <SectionLabel>Browse · {openSource.display_name}</SectionLabel>
            <BrowsePanel
              source={openSource}
              providerLabel={connector.label}
              onRefresh={() => void refresh()}
            />
          </section>
        )}
      </div>
    </div>
  );
}

function connectedAccountLabel(status: IntegrationStatus | null): string | null {
  if (!status?.connected) return null;
  if (status.accounts.length > 1) return `${status.accounts.length} accounts connected`;
  const account = status.account_email || status.account_display_name;
  return account ? `Connected as ${account}` : "Connected";
}

// The uppercase section label that runs above each block, per the mock.
function SectionLabel({ children }: { children: React.ReactNode }) {
  return (
    <div className="mb-2.5 text-[10.5px] font-bold uppercase tracking-[0.07em] text-dim">
      {children}
    </div>
  );
}

function capitalize(s: string): string {
  return s.charAt(0).toUpperCase() + s.slice(1);
}

// The noun used in the "Add a <thing>" / "<things>" section labels.
const ITEM_NOUN: Record<string, string> = {
  github_repo: "repo",
  gmail: "mailbox",
  google_drive: "folder",
  notion: "page",
  jira_project: "project",
  asana_project: "project",
  posthog_project: "project",
};

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

// The lead-in to the status line. A healthy source shows a quiet green dot; a
// syncing/failed source shows a labeled pill (failed is also surfaced in red below).
function SyncStatusMark({ syncStatus }: { syncStatus: string | null | undefined }) {
  const s = syncStatus ?? "idle";
  if (s === "idle") {
    return <span className="inline-block h-1.5 w-1.5 rounded-full bg-success" aria-label="synced" />;
  }
  const cls =
    s === "syncing"
      ? "border-blue-300/60 bg-blue-500/10 text-blue-600"
      : "border-error/40 bg-error/10 text-error";
  return (
    <span className={"inline-flex items-center rounded-full border px-2 py-0.5 text-[10.5px] font-semibold " + cls}>
      {s}
    </span>
  );
}

// A short, monospace external id for the row (the mock's "KAN" / "owner/repo").
function shortRef(source: Source): string | null {
  const ref = source.external_ref;
  if (!ref) return null;
  if (source.type === "jira_project") return ref.split(":")[1] ?? ref;
  if (source.type === "gmail") return null;
  // X / Instagram saves key on a constant "saves" ref — not worth showing.
  if (source.type === "x_saves" || source.type === "instagram_saves") return null;
  return ref;
}

function SourceRow({
  source,
  currentUser,
  highlighted,
  open,
  busySync,
  busyDelete,
  onOpen,
  onSync,
  onRemove,
}: {
  source: Source;
  currentUser: User;
  highlighted: boolean;
  open: boolean;
  busySync: boolean;
  busyDelete: boolean;
  onOpen: () => void;
  onSync: () => void;
  onRemove: () => void;
}) {
  // The row owns a live status so the item count and sync badge update as the
  // background sync runs — the parent's source list is only re-fetched on user
  // actions, so a source that finishes syncing (or gets its first documents)
  // would otherwise stay frozen at "syncing · 0 items". While syncing we poll
  // until it settles, then stop. Seeded from the parent's row so this is the
  // only thing the render reads; item_count is unknown until the first poll.
  const [status, setStatus] = useState<SourceStatus>({ ...source, item_count: null });
  // Why this row stopped tracking the sync. Distinct from `status.sync_error`,
  // which is the sync itself failing — this is us failing to observe it.
  const [pollStopped, setPollStopped] = useState<string | null>(null);
  const [shareOpen, setShareOpen] = useState(false);
  // Outside-click boundary for the share dialog: covers the "..." trigger so
  // opening the menu doesn't immediately close the dialog.
  const menuBoundaryRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    let cancelled = false;
    let timer: ReturnType<typeof setTimeout> | undefined;
    let attempts = 0;

    async function poll() {
      let next: SourceStatus;
      try {
        next = await getSourceStatus(source.source);
      } catch (e) {
        if (!cancelled) setPollStopped(e instanceof Error ? e.message : String(e));
        return;
      }
      if (cancelled) return;
      setStatus(next);
      if (next.sync_status !== "syncing") return;

      attempts += 1;
      if (attempts >= SYNC_POLL_MAX_ATTEMPTS) {
        setPollStopped("Still syncing. Stopped checking for updates — reload to resume.");
        return;
      }
      timer = setTimeout(poll, SYNC_POLL_INTERVAL_MS);
    }

    setPollStopped(null);
    void poll();
    return () => {
      cancelled = true;
      if (timer) clearTimeout(timer);
    };
    // Re-poll when the parent hands us a fresh source object (e.g. after the
    // user clicks Sync, which flips sync_status back to "syncing").
  }, [source.source, source.sync_status, source.last_synced_at]);

  // Search-driven sources (gmail, drive, …) have no local index — search hits
  // the provider live — so there's nothing to sync and no item count to show.
  const searchedLive =
    source.type === "gmail" ||
    source.type === "google_drive" ||
    source.type === "jira_project" ||
    source.type === "asana_project";
  const syncs = source.sync_enabled !== false;
  const ref = shortRef(source);

  return (
    <div
      className={
        "group flex items-center gap-3 border-b border-border px-1 py-3 last:border-b-0 " +
        (highlighted ? "-mx-2 rounded-lg bg-[var(--color-brand-50)] px-3" : "")
      }
    >
      <button type="button" onClick={onOpen} className="min-w-0 flex-1 cursor-pointer text-left">
        <div className="flex items-center gap-2 truncate text-[13.5px] font-semibold text-foreground">
          {source.display_name}
          {ref && <span className="font-mono text-[12px] font-normal text-muted-foreground">{ref}</span>}
        </div>
        <div className="mt-0.5 flex flex-wrap items-center gap-1.5 text-[12px] text-muted-foreground">
          {syncs && <SyncStatusMark syncStatus={status.sync_status} />}
          <span>
            {syncs ? (
              <>
                {relativeTime(status.last_synced_at)}
                {status.item_count !== null && ` · ${status.item_count} items`}
              </>
            ) : searchedLive ? (
              "Searched live"
            ) : (
              "live"
            )}
          </span>
        </div>
        {status.sync_status === "failed" && status.sync_error && (
          <div className="mt-1 truncate font-mono text-[11.5px] text-error">{status.sync_error}</div>
        )}
        {pollStopped && (
          <div className="mt-1 truncate text-[11.5px] text-muted-foreground">{pollStopped}</div>
        )}
      </button>
      <div className="flex shrink-0 items-center gap-1.5">
        <div className="flex items-center gap-1.5 opacity-55 transition-opacity group-hover:opacity-100">
          <button type="button" onClick={onOpen} className={rowButton()}>
            {open ? "Close" : "Browse"}
          </button>
          {syncs && (
            <button type="button" disabled={busySync} onClick={onSync} className={rowButton()}>
              {busySync ? "Syncing..." : "Sync"}
            </button>
          )}
        </div>
        {/* The menu and share dialog live outside the hover-dim group: an open
            dialog must not inherit the row's hover-dimming. */}
        <div ref={menuBoundaryRef} className="relative">
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <button
                type="button"
                aria-label="More actions"
                className="flex cursor-pointer items-center rounded-lg px-1.5 py-1.5 text-muted-foreground opacity-55 transition-opacity hover:bg-raised hover:text-foreground group-hover:opacity-100"
              >
                <MoreHorizontal className="h-4 w-4" />
              </button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end" className="w-max min-w-28">
              <DropdownMenuItem onClick={() => setShareOpen(true)}>Share</DropdownMenuItem>
              <DropdownMenuItem
                variant="destructive"
                disabled={busyDelete}
                onClick={onRemove}
              >
                Remove
              </DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>
          {shareOpen && (
            <ResourceShareDialog
              objectType="source"
              objectId={source.source}
              resourceName={source.display_name}
              resourceUrlPath={`/integrations/${providerForSourceType[source.type]}?source=${source.source}`}
              currentUser={currentUser}
              boundaryRef={menuBoundaryRef}
              onClose={() => setShareOpen(false)}
            />
          )}
        </div>
      </div>
    </div>
  );
}

// The quiet bordered row action (Browse/Sync).
function rowButton(): string {
  return "cursor-pointer rounded-lg border border-[var(--color-border)] bg-base px-3 py-1.5 text-[12px] font-semibold text-foreground hover:bg-raised disabled:opacity-60";
}

function BrowsePanel({
  source,
  providerLabel,
  onRefresh,
}: {
  source: Source;
  providerLabel: string;
  onRefresh: () => void;
}) {
  if (source.capability === "searchable") {
    return (
      <SearchablePanel
        source={source}
        providerLabel={providerLabel}
        onRefresh={onRefresh}
      />
    );
  }
  return (
    <NavigablePanel
      source={source}
      providerLabel={providerLabel}
      onRefresh={onRefresh}
    />
  );
}

// Shows the full content of one document/entry inside a browse panel, with a
// bordered header that deep-links back to the provider when a url is available.
// Hydrated saves lead with the tweet text, then a blank line, then the byline /
// reply-context / link meta. Show the tweet prominently and mute the rest.
function TweetBody({ content }: { content: string }) {
  const [body, ...rest] = content.split("\n\n");
  const meta = rest.join("\n\n").trim();
  return (
    <div className="scroll-thin max-h-96 space-y-3 overflow-auto bg-base px-4 py-4">
      <p className="whitespace-pre-wrap break-words text-[14px] leading-relaxed text-foreground">
        {body}
      </p>
      {meta && (
        <p className="whitespace-pre-wrap break-words text-[11.5px] leading-relaxed text-muted-foreground">
          {meta}
        </p>
      )}
    </div>
  );
}

function DocViewer({
  source,
  providerLabel,
  refValue,
  name,
  onClose,
}: {
  source: string;
  providerLabel: string;
  refValue: string;
  name?: string;
  onClose: () => void;
}) {
  const [content, setContent] = useState<string | null>(null);
  const [title, setTitle] = useState(name ?? "");
  const [url, setUrl] = useState<string | null>(null);
  const [media, setMedia] = useState<{ url: string; contentType: string }[]>([]);
  const [error, setError] = useState("");

  useEffect(() => {
    let cancelled = false;
    setContent(null);
    setUrl(null);
    setMedia([]);
    setError("");
    readSourceDoc(source, refValue)
      .then((doc) => {
        if (cancelled) return;
        setContent(doc.content ?? "");
        setUrl(doc.url ?? null);
        // X carries up to 4 media items (media[]); Instagram a single blob.
        if (doc.media?.length) {
          setMedia(doc.media.map((m) => ({ url: m.url, contentType: m.content_type ?? "" })));
        } else if (doc.media_url) {
          setMedia([{ url: doc.media_url, contentType: doc.media_content_type ?? "" }]);
        }
        if (doc.name) setTitle(doc.name);
      })
      .catch((e) => {
        if (!cancelled) setError(e instanceof Error ? e.message : "Could not read document");
      });
    return () => {
      cancelled = true;
    };
  }, [source, refValue]);

  return (
    <div className="mt-3 overflow-hidden rounded-lg border border-border">
      <div className="flex items-center justify-between gap-2 border-b border-border bg-surface px-3 py-2.5">
        <div className="min-w-0 truncate font-mono text-[12.5px] font-semibold text-foreground">
          {title || refValue}
        </div>
        <div className="flex shrink-0 items-center gap-3">
          {url && (
            <a
              href={url}
              target="_blank"
              rel="noreferrer"
              className="text-[12px] font-semibold text-brand hover:underline"
            >
              Open in {providerLabel} ↗
            </a>
          )}
          <button type="button" onClick={onClose} className="cursor-pointer text-[12px] text-muted-foreground hover:text-foreground">
            Close
          </button>
        </div>
      </div>
      {error ? (
        <div className="bg-base px-3 py-3 text-[12px] text-error">{error}</div>
      ) : content === null ? (
        <div className="bg-base px-3 py-3 text-[12px] text-muted-foreground">Loading…</div>
      ) : (
        <>
          {media.map((m, i) =>
            m.contentType.startsWith("video/") ? (
              // Archived social video; its transcript is in the body below.
              <video key={i} src={m.url} controls className="max-h-72 w-full bg-black" />
            ) : (
              // Presigned blob URL, not an optimizable static asset.
              // eslint-disable-next-line @next/next/no-img-element
              <img key={i} src={m.url} alt={title} className="max-h-72 w-full bg-black object-contain" />
            ),
          )}
          <TweetBody content={content} />
        </>
      )}
    </div>
  );
}

function SearchablePanel({
  source,
  providerLabel,
  onRefresh,
}: {
  source: Source;
  providerLabel: string;
  onRefresh: () => void;
}) {
  const [query, setQuery] = useState("");
  const [hits, setHits] = useState<SourceSearchHit[] | null>(null);
  const [searchError, setSearchError] = useState<string | null>(null);
  const [recent, setRecent] = useState<SourceEntry[] | null>(null);
  const [searching, setSearching] = useState(false);
  const [openDoc, setOpenDoc] = useState<{ ref: string; name?: string } | null>(null);

  const showHistory = source.type === "slack" || source.type === "gong_calls";

  useEffect(() => {
    let cancelled = false;
    getSourceEntries(source.source)
      .then((entries) => {
        if (!cancelled) setRecent(entries);
      })
      .catch(() => {
        if (!cancelled) setRecent([]);
      });
    return () => {
      cancelled = true;
    };
  }, [source.source]);

  async function search() {
    if (!query.trim()) return;
    setSearching(true);
    setSearchError(null);
    try {
      setHits(await searchSource(query, source.source));
    } catch (e) {
      // A scoped provider failure (rate limit, disconnected connection) must
      // never read as "No matches."
      setHits(null);
      setSearchError(e instanceof Error ? e.message : "Search failed");
    } finally {
      setSearching(false);
    }
  }

  return (
    <div>
      <form
        onSubmit={(e) => {
          e.preventDefault();
          void search();
        }}
        className="mb-3 flex gap-2"
      >
        <input
          type="search"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder={`Search ${source.display_name}…`}
          className="flex-1 rounded-lg border border-[var(--color-border)] bg-base px-3 py-2 text-[13px] text-foreground placeholder:text-muted-foreground focus:border-brand focus:outline-none"
        />
        <button type="submit" disabled={searching || !query.trim()} className={primaryButton()}>
          {searching ? "Searching..." : "Search"}
        </button>
      </form>

      {searchError && (
        <div className="mb-2 px-1.5 py-1 text-[12.5px] text-error">{searchError}</div>
      )}

      {hits !== null && (() => {
        const realHits = hits.filter((hit) => hit.ref);
        const truncation = hits.find((hit) => hit.truncated);
        return (
          <div className="mb-2">
            {realHits.length === 0 ? (
              <div className="px-1.5 py-1 text-[12.5px] text-muted-foreground">No matches.</div>
            ) : (
              realHits.map((hit) => {
                const isOpen = openDoc?.ref === hit.ref;
                return (
                  <div key={hit.ref}>
                    <HitRow
                      hitKey={hit.ref!}
                      label={hit.name}
                      snippet={hit.snippet}
                      open={isOpen}
                      onOpen={() => setOpenDoc(isOpen ? null : { ref: hit.ref!, name: hit.name })}
                    />
                    {isOpen && (
                      <DocViewer
                        source={source.source}
                        providerLabel={providerLabel}
                        refValue={hit.ref!}
                        name={hit.name}
                        onClose={() => setOpenDoc(null)}
                      />
                    )}
                  </div>
                );
              })
            )}
            {truncation && (
              <div className="px-1.5 py-1 text-[12px] text-muted-foreground">
                Showing the first {truncation.returned}
                {truncation.estimated_total ? ` of ~${truncation.estimated_total}` : ""} matches —
                narrow your search to see more.
              </div>
            )}
          </div>
        );
      })()}

      {hits === null && recent && recent.length > 0 && (
        <div className="mb-2">
          {recent.map((entry) => {
            const ref = entry.id ?? entry.path ?? entry.name;
            const isOpen = openDoc?.ref === ref;
            return (
              <div key={ref}>
                <HitRow
                  hitKey={ref}
                  label={entry.name}
                  snippet={entry.snippet ?? undefined}
                  open={isOpen}
                  onOpen={() => setOpenDoc(isOpen ? null : { ref, name: entry.name })}
                />
                {isOpen && (
                  <DocViewer
                    source={source.source}
                    providerLabel={providerLabel}
                    refValue={ref}
                    name={entry.name}
                    onClose={() => setOpenDoc(null)}
                  />
                )}
              </div>
            );
          })}
        </div>
      )}

      {showHistory && (
        <HistoryControl source={source} onFetched={onRefresh} />
      )}
    </div>
  );
}

// A quiet browse hit row: a monospace key, then the title (the mock's
// "KAN-2  Task 2"). When the key and label coincide, just shows the label.
function HitRow({
  hitKey,
  label,
  snippet,
  open,
  onOpen,
}: {
  hitKey: string;
  label?: string;
  snippet?: string;
  open?: boolean;
  onOpen: () => void;
}) {
  // An X save that hasn't hydrated yet has no title — its name is still the raw
  // numeric tweet id. Show "Loading…" instead of a wall of numbers.
  const pending = !!label && /^\d+$/.test(label);
  const showKey = !pending && !!label && label !== hitKey && !label.startsWith(hitKey);
  return (
    <button
      type="button"
      onClick={onOpen}
      className={
        "block w-full cursor-pointer rounded-md px-1.5 py-1.5 text-left hover:bg-raised " +
        (open ? "bg-raised" : "")
      }
    >
      <div className="flex items-baseline gap-2.5">
        {showKey && <span className="font-mono text-[12px] text-muted-foreground">{hitKey}</span>}
        {pending ? (
          <span className="min-w-0 truncate text-[13px] italic text-muted-foreground">Loading…</span>
        ) : (
          <span className="min-w-0 truncate text-[13px] text-foreground">{label || hitKey}</span>
        )}
      </div>
      {snippet && <div className="mt-0.5 truncate text-[11.5px] text-muted-foreground">{snippet}</div>}
    </button>
  );
}

function NavigablePanel({
  source,
  providerLabel,
  onRefresh,
}: {
  source: Source;
  providerLabel: string;
  onRefresh: () => void;
}) {
  const [path, setPath] = useState("");
  const [entries, setEntries] = useState<SourceEntry[] | null>(null);
  const [hasMore, setHasMore] = useState(false);
  const [loadingMore, setLoadingMore] = useState(false);
  const [crumbs, setCrumbs] = useState<{ label: string; path: string }[]>([{ label: source.display_name, path: "" }]);
  const [openDoc, setOpenDoc] = useState<{ ref: string; name?: string } | null>(null);
  const [error, setError] = useState("");
  // Bumped whenever the listing target changes, so an in-flight Load more for
  // the previous directory can't clobber the new one.
  const listingSeq = useRef(0);

  // The endpoint truncates at the requested limit; asking for one extra row is
  // how callers detect that another page exists (see routers/sources.py).
  const PAGE_SIZE = 200;

  async function fetchPage(dir: string, after: string): Promise<{ page: SourceEntry[]; more: boolean }> {
    const rows = await getSourceEntries(source.source, dir, { limit: PAGE_SIZE + 1, after });
    const more = rows.length > PAGE_SIZE;
    return { page: more ? rows.slice(0, PAGE_SIZE) : rows, more };
  }

  useEffect(() => {
    const seq = ++listingSeq.current;
    setEntries(null);
    setHasMore(false);
    setError("");
    fetchPage(path, "")
      .then(({ page, more }) => {
        if (listingSeq.current !== seq) return;
        setEntries(page);
        setHasMore(more);
      })
      .catch((e) => {
        if (listingSeq.current !== seq) return;
        setEntries([]);
        setError(e instanceof Error ? e.message : "Could not list entries");
      });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [source.source, path]);

  async function loadMore(all: boolean) {
    if (!entries || loadingMore) return;
    const seq = listingSeq.current;
    setLoadingMore(true);
    try {
      let acc = entries;
      let more = hasMore;
      while (more) {
        const cursor = acc[acc.length - 1]?.path;
        if (!cursor) break; // the cursor is a path; a path-less listing can't page
        const { page, more: nextMore } = await fetchPage(path, cursor);
        if (listingSeq.current !== seq) return;
        acc = [...acc, ...page];
        more = nextMore;
        if (!all) break;
      }
      setEntries(acc);
      setHasMore(more);
    } catch (e) {
      if (listingSeq.current === seq) {
        setError(e instanceof Error ? e.message : "Could not list entries");
      }
    } finally {
      if (listingSeq.current === seq) setLoadingMore(false);
    }
  }

  // The entries endpoint returns every descendant file as a flat, path-ordered
  // list (the VFS builds its tree from the same shape). Fold that into one
  // directory level: an entry nested below the current path becomes a folder
  // row for its first path segment, emitted once, in path order.
  const visibleEntries = useMemo(() => {
    if (!entries) return null;
    const dirPrefix = path ? `${path}/` : "";
    const seenFolders = new Set<string>();
    const rows: SourceEntry[] = [];
    for (const entry of entries) {
      const rel = entry.path?.startsWith(dirPrefix) ? entry.path.slice(dirPrefix.length) : null;
      const slash = rel?.indexOf("/") ?? -1;
      if (rel === null || slash === -1) {
        rows.push(entry);
        continue;
      }
      const segment = rel.slice(0, slash);
      if (seenFolders.has(segment)) continue;
      seenFolders.add(segment);
      rows.push({ name: segment, kind: "dir", path: `${dirPrefix}${segment}` });
    }
    return rows;
  }, [entries, path]);

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
    <div>
      <div className="mb-2 flex flex-wrap items-center gap-1 text-[12px] text-muted-foreground">
        {crumbs.map((c, i) => (
          <span key={c.path + i} className="flex items-center gap-1">
            {i > 0 && <span className="text-muted-foreground/60">/</span>}
            <button
              type="button"
              onClick={() => goCrumb(i)}
              className={"cursor-pointer " + (i === crumbs.length - 1 ? "text-foreground" : "hover:text-foreground hover:underline")}
            >
              {c.label}
            </button>
          </span>
        ))}
      </div>

      {error && <div className="mb-2 text-[12px] text-error">{error}</div>}

      {visibleEntries === null ? (
        <div className="text-[12px] text-muted-foreground">Loading…</div>
      ) : visibleEntries.length === 0 ? (
        <div className="text-[12px] text-muted-foreground">Empty.</div>
      ) : (
        <div className="space-y-0.5">
          {visibleEntries.map((entry) => {
            const folder = isFolder(entry);
            const ref = entry.id ?? entry.path ?? entry.name;
            const isOpen = !folder && openDoc?.ref === ref;
            // An un-hydrated save still has its raw numeric tweet id as its name.
            const pending = !folder && /^\d+$/.test(entry.name);
            const key = `${folder ? "dir" : "doc"}:${ref}`;
            return (
              <div key={key}>
                <button
                  type="button"
                  onClick={() => openEntry(entry)}
                  className={
                    "flex w-full cursor-pointer items-start gap-2 rounded-md px-2 py-1.5 text-left hover:bg-raised " +
                    (isOpen ? "bg-raised" : "")
                  }
                >
                  <span aria-hidden className="text-[13px] leading-5">
                    {folder ? "📁" : "📄"}
                  </span>
                  <span className="min-w-0 flex-1">
                    {pending ? (
                      <span className="truncate text-[12.5px] italic text-muted-foreground">Loading…</span>
                    ) : (
                      <span className="block truncate text-[12.5px] text-foreground">{entry.name}</span>
                    )}
                    {entry.snippet && !pending && (
                      <span className="mt-0.5 block truncate text-[11.5px] text-muted-foreground">
                        {entry.snippet}
                      </span>
                    )}
                  </span>
                </button>
                {isOpen && (
                  <DocViewer
                    source={source.source}
                    providerLabel={providerLabel}
                    refValue={ref}
                    name={entry.name}
                    onClose={() => setOpenDoc(null)}
                  />
                )}
              </div>
            );
          })}
          {hasMore && (
            <div className="flex items-center gap-3 px-2 py-1.5 text-[12px] text-muted-foreground">
              {loadingMore ? (
                <span>Loading…</span>
              ) : (
                <>
                  <button
                    type="button"
                    onClick={() => loadMore(false)}
                    className="cursor-pointer hover:text-foreground hover:underline"
                  >
                    Load more
                  </button>
                  <button
                    type="button"
                    onClick={() => loadMore(true)}
                    className="cursor-pointer hover:text-foreground hover:underline"
                  >
                    Load all
                  </button>
                </>
              )}
            </div>
          )}
        </div>
      )}

      {source.type === "slack" || source.type === "gong_calls" ? (
        <HistoryControl source={source} onFetched={onRefresh} />
      ) : null}
    </div>
  );
}

function HistoryControl({
  source,
  onFetched,
}: {
  source: Source;
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
      const result = await fetchSourceHistory(source.source, since, until || undefined);
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
      <div className="mb-2 text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">Fetch older history</div>
      <div className="flex flex-wrap items-center gap-2">
        <label className="text-[11.5px] text-muted-foreground">
          Since
          <input
            type="date"
            value={since}
            onChange={(e) => setSince(e.target.value)}
            className="ml-1 rounded-md border border-border bg-surface px-2 py-1 text-[12px] text-foreground focus:border-brand focus:outline-none"
          />
        </label>
        <label className="text-[11.5px] text-muted-foreground">
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
        {message && <span className="text-[11.5px] text-muted-foreground">{message}</span>}
      </div>
    </div>
  );
}
