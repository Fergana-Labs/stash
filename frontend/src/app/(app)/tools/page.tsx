"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { Globe, Plus, Terminal } from "lucide-react";
import { toast } from "sonner";
import { useBreadcrumbs } from "@/components/BreadcrumbContext";
import { useAuth } from "@/hooks/useAuth";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Skeleton } from "@/components/ui/skeleton";
import {
  ApiError,
  createMcpServer,
  deleteMcpServer,
  listMcpServers,
  listSources,
  type McpServer,
  type Source,
} from "@/lib/api";
import {
  INTEGRATIONS_CHANGED_EVENT,
  listIntegrations,
  startConnect,
  type IntegrationStatus,
} from "@/lib/integrations";
import {
  CONNECTORS,
  connectorIcon,
  providerForSourceType,
  type Connector,
} from "@/components/integrations/connectors";
import PaywallModal from "@/components/PaywallModal";

// One row per connector — the standard integrations list. The row is a link
// to the provider's page (manage, pick sources, disconnect). For OAuth
// providers the Connect button skips the page and goes straight to the
// consent screen, returning here; api-key and extension providers still
// route through their page (credential form / extension install).
function IntegrationRow({
  connector,
  connected,
  busy,
  onOauthConnect,
}: {
  connector: Connector;
  connected: boolean;
  busy: boolean;
  onOauthConnect: (() => void) | null;
}) {
  return (
    <Link
      href={`/integrations/${connector.provider}`}
      className="group flex items-center gap-4 px-4 py-3.5 transition-colors hover:bg-raised"
    >
      <span className="flex h-7 w-7 shrink-0 items-center justify-center [&_img]:h-6 [&_img]:w-6 [&_svg]:h-6 [&_svg]:w-6">
        {connectorIcon(connector.provider)}
      </span>
      <div className="min-w-0 flex-1">
        <div className="text-[13.5px] font-semibold text-foreground">{connector.label}</div>
        <p className="truncate text-[12.5px] text-dim">{connector.blurb}</p>
      </div>
      {connected ? (
        <span className="flex shrink-0 items-center gap-1.5 text-[12px] font-medium text-[var(--color-success)]">
          <span className="h-1.5 w-1.5 rounded-full bg-[var(--color-success)]" />
          Connected
        </span>
      ) : onOauthConnect ? (
        <button
          type="button"
          onClick={(e) => {
            e.preventDefault();
            e.stopPropagation();
            onOauthConnect();
          }}
          disabled={busy}
          className="shrink-0 cursor-pointer text-[12px] font-medium text-muted-foreground transition-colors hover:text-brand-700 disabled:cursor-not-allowed"
        >
          {busy ? "Connecting…" : "Connect"}
        </button>
      ) : (
        <span className="shrink-0 text-[12px] font-medium text-muted-foreground transition-colors group-hover:text-brand-700">
          Connect
        </span>
      )}
    </Link>
  );
}

function IntegrationsGrid() {
  // Extension connectors have no token — source presence is their "connected".
  // OAuth/api-key connectors use the integration status, so a provider that
  // was disconnected with its data kept reads "Connect", not "Connected".
  const [sourceProviders, setSourceProviders] = useState<Set<string>>(new Set());
  const [statuses, setStatuses] = useState<Record<string, IntegrationStatus> | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [paywalled, setPaywalled] = useState(false);

  // Straight to the consent screen; the OAuth flow returns to /tools, where
  // the row reads Connected. No successful-return path resets `busy` — the
  // whole page navigates away.
  async function connectNow(connector: Connector) {
    setBusy(connector.provider);
    try {
      await startConnect(connector.provider, "/tools");
    } catch (e) {
      if (e instanceof ApiError && e.status === 402) setPaywalled(true);
      else toast.error(e instanceof Error ? e.message : "Could not start connection");
      setBusy(null);
    }
  }

  useEffect(() => {
    const load = () => {
      listSources()
        .then((all) => setSourceProviders(new Set(all.map((s: Source) => providerForSourceType[s.type] ?? s.type))))
        .catch(() => {});
      listIntegrations()
        .then((r) => {
          const byProvider: Record<string, IntegrationStatus> = {};
          for (const p of r.providers) byProvider[p.provider] = p;
          setStatuses(byProvider);
        })
        .catch(() => {});
    };
    load();
    window.addEventListener(INTEGRATIONS_CHANGED_EVENT, load);
    return () => window.removeEventListener(INTEGRATIONS_CHANGED_EVENT, load);
  }, []);

  if (statuses === null) {
    return (
      <div className="flex flex-col gap-2">
        {Array.from({ length: 6 }, (_, i) => (
          <Skeleton key={i} className="h-[54px] rounded-lg" />
        ))}
      </div>
    );
  }

  // The server omits providers this user may not use (customer-specific
  // integrations like Heavi) — extension connectors are always available.
  const rows = CONNECTORS.filter((c) => c.kind === "extension" || c.provider in statuses);
  return (
    <div className="divide-y divide-border overflow-hidden rounded-xl border border-border bg-surface">
      {rows.map((c) => {
        const status = statuses[c.provider];
        const oauth =
          c.kind !== "extension" && status?.auth_kind !== "api_key" && !status?.disabled_reason;
        return (
          <IntegrationRow
            key={c.provider}
            connector={c}
            connected={c.kind === "extension" ? sourceProviders.has(c.provider) : !!status?.connected}
            busy={busy === c.provider}
            onOauthConnect={oauth ? () => void connectNow(c) : null}
          />
        );
      })}
      {paywalled && <PaywallModal onClose={() => setPaywalled(false)} />}
    </div>
  );
}

// One "KEY=VALUE" line per header, parsed at submit time.
function parseHeaderLines(raw: string): Record<string, string> {
  const headers: Record<string, string> = {};
  for (const line of raw.split("\n")) {
    const trimmed = line.trim();
    if (!trimmed) continue;
    const eq = trimmed.indexOf("=");
    if (eq <= 0) throw new Error(`Headers must be KEY=VALUE lines; got "${trimmed}"`);
    headers[trimmed.slice(0, eq).trim()] = trimmed.slice(eq + 1).trim();
  }
  return headers;
}

function AddServerForm({ onAdded }: { onAdded: () => void }) {
  const [name, setName] = useState("");
  const [transport, setTransport] = useState<"stdio" | "http">("http");
  const [command, setCommand] = useState("");
  const [url, setUrl] = useState("");
  const [headerLines, setHeaderLines] = useState("");
  const [saving, setSaving] = useState(false);

  async function submit() {
    setSaving(true);
    try {
      const headers = transport === "http" ? parseHeaderLines(headerLines) : {};
      await createMcpServer({
        name: name.trim(),
        transport,
        ...(transport === "stdio" ? { command: command.trim() } : { url: url.trim(), headers }),
      });
      setName("");
      setCommand("");
      setUrl("");
      setHeaderLines("");
      onAdded();
    } catch (e) {
      toast.error(e instanceof ApiError || e instanceof Error ? e.message : "Failed to add server");
    } finally {
      setSaving(false);
    }
  }

  const targetMissing = transport === "stdio" ? !command.trim() : !url.trim();

  return (
    <form
      className="rounded-lg border border-border bg-surface p-4"
      onSubmit={(e) => {
        e.preventDefault();
        void submit();
      }}
    >
      <h2 className="text-sm font-semibold">Add an MCP server</h2>
      <div className="mt-3 flex flex-col gap-3">
        <Input
          aria-label="Server name"
          placeholder="Name (e.g. linear)"
          value={name}
          onChange={(e) => setName(e.target.value)}
        />
        <div className="flex gap-1 rounded-md bg-muted p-1 self-start" role="radiogroup">
          {(["http", "stdio"] as const).map((t) => (
            <button
              key={t}
              type="button"
              role="radio"
              aria-checked={transport === t}
              onClick={() => setTransport(t)}
              className={`rounded px-3 py-1 text-xs font-medium ${
                transport === t
                  ? "bg-surface text-foreground shadow-sm"
                  : "text-muted-foreground"
              }`}
            >
              {t === "http" ? "Remote (HTTP)" : "Local (stdio)"}
            </button>
          ))}
        </div>
        {transport === "stdio" ? (
          <Input
            aria-label="Command"
            placeholder="Command (e.g. npx -y linear-mcp)"
            value={command}
            onChange={(e) => setCommand(e.target.value)}
          />
        ) : (
          <>
            <Input
              aria-label="URL"
              placeholder="URL (e.g. https://mcp.example.com/mcp)"
              value={url}
              onChange={(e) => setUrl(e.target.value)}
            />
            <Textarea
              aria-label="Headers"
              placeholder={"Optional headers, one per line:\nAuthorization=Bearer …"}
              rows={2}
              value={headerLines}
              onChange={(e) => setHeaderLines(e.target.value)}
            />
          </>
        )}
        <Button type="submit" disabled={saving || !name.trim() || targetMissing} className="self-start">
          <Plus className="h-4 w-4" />
          Add server
        </Button>
      </div>
    </form>
  );
}

function ServerRow({ server, onRemoved }: { server: McpServer; onRemoved: () => void }) {
  const [removing, setRemoving] = useState(false);

  async function remove() {
    setRemoving(true);
    try {
      await deleteMcpServer(server.id);
      onRemoved();
    } catch (e) {
      toast.error(e instanceof ApiError ? e.message : "Failed to remove server");
      setRemoving(false);
    }
  }

  const headerKeys = Object.keys(server.headers);
  return (
    <li className="flex items-center gap-3 rounded-lg border border-border bg-surface px-4 py-3">
      {server.transport === "stdio" ? (
        <Terminal className="h-4 w-4 shrink-0 text-muted-foreground" />
      ) : (
        <Globe className="h-4 w-4 shrink-0 text-muted-foreground" />
      )}
      <div className="min-w-0 flex-1">
        <div className="text-sm font-medium">{server.name}</div>
        <div className="truncate text-xs text-muted-foreground">
          {server.transport === "stdio" ? server.command : server.url}
          {headerKeys.length > 0 && `, headers: ${headerKeys.join(", ")}`}
        </div>
      </div>
      <Button variant="ghost" size="sm" onClick={() => void remove()} disabled={removing}>
        Remove
      </Button>
    </li>
  );
}

export default function ToolsPage() {
  const router = useRouter();
  const { user, loading } = useAuth();
  const [servers, setServers] = useState<McpServer[] | null>(null);

  useBreadcrumbs([{ label: "Tools" }], "tools");

  const refresh = useCallback(async () => {
    try {
      setServers(await listMcpServers());
    } catch (e) {
      toast.error(e instanceof ApiError ? e.message : "Failed to load MCP servers");
    }
  }, []);

  useEffect(() => {
    if (!loading && !user) router.push("/login");
  }, [user, loading, router]);

  useEffect(() => {
    if (user) void refresh();
  }, [user, refresh]);

  if (loading || !user) return null;

  return (
    <div className="h-full overflow-y-auto">
      <div className="mx-auto flex max-w-5xl flex-col gap-8 px-8 py-7">
        <div>
          <h1 className="font-display text-[22px] font-semibold tracking-tight text-foreground">
            Tools
          </h1>
          <p className="mt-1 text-sm text-muted-foreground">
            Everything your agent can reach — connected sources and MCP servers.
          </p>
        </div>

        <section>
          <h2 className="text-[15px] font-semibold text-foreground">Integrations</h2>
          <p className="mt-0.5 text-[13px] text-muted-foreground">
            Connect accounts and choose what your agent can read. Click one to connect or manage
            it.
          </p>
          <div className="mt-4">
            <IntegrationsGrid />
          </div>
        </section>

        <section>
          <h2 className="text-[15px] font-semibold text-foreground">MCP servers</h2>
          <p className="mt-0.5 text-[13px] text-muted-foreground">
            Available to your cloud agent, and installable locally with{" "}
            <code className="text-xs">stash tools install</code>.
          </p>
          <div className="mt-4 flex flex-col gap-3">
            {servers !== null && servers.length === 0 && (
              <p className="text-sm text-muted-foreground">No MCP servers yet — add one below.</p>
            )}
            {servers !== null && servers.length > 0 && (
              <ul className="flex flex-col gap-2">
                {servers.map((s) => (
                  <ServerRow key={s.id} server={s} onRemoved={() => void refresh()} />
                ))}
              </ul>
            )}
            <AddServerForm onAdded={() => void refresh()} />
          </div>
        </section>
      </div>
    </div>
  );
}
