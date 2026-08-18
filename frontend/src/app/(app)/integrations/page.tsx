"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useState, type ReactNode } from "react";
import { useRouter } from "next/navigation";
import { Globe, Server, SquareTerminal } from "lucide-react";
import { toast } from "sonner";

import { useBreadcrumbs } from "@/components/BreadcrumbContext";
import { useAuth } from "@/hooks/useAuth";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import {
  ApiError,
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
import {
  AGENT_COPY,
  CODING_AGENTS,
  agentDialogBody,
} from "@/components/integrations/CodingAgents";
import { OUTPUT_SURFACES } from "@/components/integrations/OutputSurfaces";
import AddServerForm from "@/components/integrations/McpServers";
import PaywallModal from "@/components/PaywallModal";
import { ChromeIcon } from "@/components/integrations/BrandIcons";
import { cn } from "@/lib/utils";

// One flat grid. Every way anything reaches Stash, or reads it back, is a box
// with the same shape — the only structure is a direction badge and a search
// field. Sections used to group these, but the groupings were a second
// vocabulary to learn on top of the boxes themselves.
type Direction = "in" | "out";

// The list reads in the order a team adopts Stash: the agents they already
// run, then the tools their work lives in, then the personal accounts they
// save to.
const TIER = { agents: 0, work: 1, personal: 2 };

// Consumer accounts — the "save your own stuff" end of the list rather than
// the ones a team wires up first.
const PERSONAL_PROVIDERS = new Set(["x", "instagram"]);

type Box = {
  key: string;
  name: string;
  direction: Direction;
  blurb: string;
  icon: ReactNode;
  /** Connected boxes sort to the front of their tier. */
  active: boolean;
  /** Which band of the list this belongs to; see TIER. */
  tier: number;
  /** Sorts to the end of its tier — for the "add one" affordance. */
  sortLast?: boolean;
  /** Everything the search field matches against. */
  search: string;
  /** What the dialog holds: setup steps, or an integration's own settings. */
  dialog?: { title: string; description: string; body: ReactNode };
  /** Verb on the button that opens the dialog. */
  actionLabel?: string;
  /** For the one box that isn't a detail view: opens the add-server form. */
  onAction?: () => void;
  action: ReactNode;
};

function IntegrationBox({ box, onOpen }: { box: Box; onOpen?: () => void }) {
  return (
    <div
      className={cn(
        "flex flex-col gap-2.5 rounded-xl border p-4",
        box.active
          ? "border-success/30 bg-success/[0.06]"
          : "border-border bg-surface",
      )}
    >
      <div className="flex items-center gap-2.5">
        <span className="flex h-7 w-7 shrink-0 items-center justify-center [&_img]:h-6 [&_img]:w-6 [&_svg]:h-6 [&_svg]:w-6">
          {box.icon}
        </span>
        {onOpen ? (
          <button
            type="button"
            onClick={onOpen}
            className="min-w-0 flex-1 truncate text-left text-[14px] font-medium text-foreground hover:underline"
          >
            {box.name}
          </button>
        ) : (
          <span className="min-w-0 flex-1 truncate text-[14px] font-medium text-foreground">
            {box.name}
          </span>
        )}
      </div>

      <p className="min-h-[34px] break-words text-[12.5px] leading-snug text-muted-foreground">
        {box.blurb}
      </p>

      {box.action}
    </div>
  );
}

/** A source connector's detail view. Also the only place `disabled_reason`
 *  is ever shown: a server without INTEGRATIONS_ENCRYPTION_KEY offers a
 *  Connect button that can only 503, and until now said nothing about why. */
function ConnectorDialogBody({
  connector,
  status,
  connected,
  busy,
  onConnect,
}: {
  connector: Connector;
  status: IntegrationStatus | undefined;
  connected: boolean;
  busy: boolean;
  onConnect: (() => void) | null;
}) {
  return (
    <div className="flex min-w-0 flex-col gap-3">
      {status?.disabled_reason && (
        <p className="rounded-lg border border-warning/30 bg-chart-5/10 px-3 py-2 text-[12.5px] text-warning">
          {status.disabled_reason}
        </p>
      )}
      <p className="text-[12.5px] text-muted-foreground">
        {connected
          ? "Connected. Choose what syncs, check sync status, or disconnect on its settings page."
          : "Connecting opens the provider's consent screen. Nothing syncs until you pick what to include."}
      </p>
      <div className="flex flex-wrap items-center gap-2">
        {!connected && onConnect && (
          <Button size="sm" disabled={busy} onClick={onConnect}>
            {busy ? "Connecting…" : `Connect ${connector.label}`}
          </Button>
        )}
        <Button asChild size="sm" variant={connected || !onConnect ? "secondary" : "ghost"}>
          <Link href={`/integrations/${connector.provider}`}>
            {connected ? "Manage sources" : `Open ${connector.label} settings`}
          </Link>
        </Button>
      </div>
    </div>
  );
}

/** A lucide glyph in the same tile the brand marks sit in, so a box with no
 *  logo still lines up with one that has. */
function TileIcon({ icon: Icon }: { icon: typeof Globe }) {
  return (
    <span className="flex h-7 w-7 items-center justify-center rounded-md bg-raised">
      <Icon className="h-4 w-4 text-dim" />
    </span>
  );
}

/** What a registered server points at, in words: a remote host, or a local
 *  process named by the binary it runs. */
function mcpServerTarget(server: McpServer): string {
  if (server.transport === "stdio") {
    const binary = (server.command ?? "").trim().split(/\s+/)[0];
    return binary ? `a local ${binary} process` : "a local process";
  }
  try {
    return new URL(server.url!).hostname;
  } catch {
    return "a remote server";
  }
}

function mcpServerIcon(server: McpServer) {
  if (server.url && new URL(server.url).hostname === "mcp.linear.app") {
    return connectorIcon("linear");
  }

  return <TileIcon icon={server.transport === "stdio" ? SquareTerminal : Globe} />;
}

export default function IntegrationsPage() {
  const router = useRouter();
  const { user, loading } = useAuth();
  const [sourceProviders, setSourceProviders] = useState<Set<string>>(new Set());
  const [statuses, setStatuses] = useState<Record<string, IntegrationStatus> | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [servers, setServers] = useState<McpServer[]>([]);
  const [query, setQuery] = useState("");
  const [direction, setDirection] = useState<Direction>("in");
  const [open, setOpen] = useState<Box | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [paywalled, setPaywalled] = useState(false);
  const [addingServer, setAddingServer] = useState(false);

  useBreadcrumbs([{ label: "Connect" }], "integrations");

  useEffect(() => {
    if (!loading && !user) router.push("/login");
  }, [user, loading, router]);

  // Both calls decide what a box says — statuses which boxes exist, sources
  // whether an extension box reads Connected — so either one failing makes
  // the whole grid wrong. Fail together, loudly, instead of showing a grid
  // that lies or skeletons that never resolve.
  useEffect(() => {
    const load = () => {
      setLoadError(null);
      Promise.all([listSources(), listIntegrations()])
        .then(([sources, integrations]) => {
          setSourceProviders(new Set(sources.map((s: Source) => providerForSourceType[s.type])));
          const byProvider: Record<string, IntegrationStatus> = {};
          for (const p of integrations.providers) byProvider[p.provider] = p;
          setStatuses(byProvider);
        })
        .catch((e) =>
          setLoadError(e instanceof Error ? e.message : "Failed to load integrations"),
        );
    };
    load();
    window.addEventListener(INTEGRATIONS_CHANGED_EVENT, load);
    return () => window.removeEventListener(INTEGRATIONS_CHANGED_EVENT, load);
  }, []);

  const refreshServers = useCallback(async () => {
    try {
      setServers(await listMcpServers());
    } catch (e) {
      toast.error(e instanceof ApiError ? e.message : "Failed to load MCP servers");
    }
  }, []);

  useEffect(() => {
    void refreshServers();
  }, [refreshServers]);

  const isConnected = useCallback(
    (c: Connector) =>
      c.kind === "extension"
        ? sourceProviders.has(c.provider)
        : !!statuses?.[c.provider]?.connected,
    [sourceProviders, statuses],
  );

  // Straight to the consent screen; the OAuth flow returns to /integrations,
  // where the box reads Connected. No successful-return path resets `busy` —
  // the whole page navigates away.
  const connectNow = useCallback(async (connector: Connector) => {
    setBusy(connector.provider);
    try {
      await startConnect(connector.provider, "/integrations");
    } catch (e) {
      if (e instanceof ApiError && e.status === 402) setPaywalled(true);
      else toast.error(e instanceof Error ? e.message : "Could not start connection");
      setBusy(null);
    }
  }, []);

  const removeServer = useCallback(
    async (id: string) => {
      try {
        await deleteMcpServer(id);
        await refreshServers();
      } catch (e) {
        toast.error(e instanceof ApiError ? e.message : "Failed to remove server");
      }
    },
    [refreshServers],
  );

  const boxes = useMemo<Box[]>(() => {
    if (!statuses) return [];

    // The server omits providers this user may not use (customer-specific
    // integrations like Heavi) — extension connectors are always available.
    const connectors = CONNECTORS.filter((c) => c.kind === "extension" || c.provider in statuses);

    const sourceBoxes: Omit<Box, "action">[] = connectors.map((c) => {
      const connected = isConnected(c);
      const status = statuses[c.provider];
      const oauth =
        c.kind !== "extension" && status?.auth_kind !== "api_key" && !status?.disabled_reason;
      return {
        key: `source:${c.provider}`,
        name: c.label,
        direction: "in" as const,
        blurb: c.blurb,
        icon: connectorIcon(c.provider),
        active: connected,
        tier: PERSONAL_PROVIDERS.has(c.provider) ? TIER.personal : TIER.work,
        search: `${c.label} ${c.blurb} ${c.provider} source`,
        actionLabel: connected ? "Manage" : "Connect",
        dialog: {
          title: c.label,
          description: c.blurb,
          body: (
            <ConnectorDialogBody
              connector={c}
              status={status}
              connected={connected}
              busy={busy === c.provider}
              onConnect={oauth ? () => void connectNow(c) : null}
            />
          ),
        },
      };
    });

    const browserBox: Omit<Box, "action"> = {
      key: "browser",
      name: "Stash for Chrome",
      direction: "in",
      blurb: "Clip any page or every open tab, import your bookmarks, keep your saves in sync.",
      icon: <ChromeIcon />,
      active: false,
      tier: TIER.personal,
      search: "browser chrome extension clip bookmarks tabs",
      actionLabel: "Connect",
      dialog: {
        title: "Stash for Chrome",
        description: "Save from the browser without leaving the page.",
        body: (
          <div className="flex min-w-0 flex-col gap-3">
            <ul className="flex list-disc flex-col gap-1 pl-4 text-[12.5px] text-muted-foreground">
              <li>Clip any page, or every open tab at once.</li>
              <li>Import your bookmarks — Stash fetches what&apos;s behind each link.</li>
              <li>Keep your X and Instagram saves in sync.</li>
              <li>Stream your ChatGPT and Claude chats in.</li>
            </ul>
            <Button asChild size="sm" className="self-start">
              <Link href="/extension">Get the extension</Link>
            </Button>
          </div>
        ),
      },
    };

    const serverBoxes: Omit<Box, "action">[] = servers.map((s) => ({
      key: `mcp:${s.id}`,
      name: s.name,
      direction: "in",
      // Every other box describes itself in a sentence; a bare URL here read
      // as a missing description. The exact target and header names are one
      // click away in Manage.
      blurb: `Tools from ${mcpServerTarget(s)}, handed to your cloud agent before every turn.`,
      icon: mcpServerIcon(s),
      active: true,
      tier: TIER.work,
      search: `${s.name} mcp server tool ${s.url ?? ""} ${s.command ?? ""}`,
      actionLabel: "Manage",
      dialog: {
        title: s.name,
        description: "An MCP server your cloud agent can call before every turn.",
        body: (
          <div className="flex min-w-0 flex-col gap-3">
            <dl className="flex flex-col gap-2 text-[12.5px]">
              <div className="flex gap-2">
                <dt className="w-20 shrink-0 text-muted-foreground">Transport</dt>
                <dd className="font-mono">
                  {s.transport === "stdio" ? "Local (stdio)" : "Remote (HTTP)"}
                </dd>
              </div>
              <div className="flex gap-2">
                <dt className="w-20 shrink-0 text-muted-foreground">
                  {s.transport === "stdio" ? "Command" : "URL"}
                </dt>
                <dd className="min-w-0 break-all font-mono">
                  {s.transport === "stdio" ? s.command : s.url}
                </dd>
              </div>
              {Object.keys(s.headers).length > 0 && (
                <div className="flex gap-2">
                  <dt className="w-20 shrink-0 text-muted-foreground">Headers</dt>
                  {/* Values are secrets — the registry only ever shows key names. */}
                  <dd className="min-w-0 break-all font-mono">
                    {Object.keys(s.headers).join(", ")}
                  </dd>
                </div>
              )}
            </dl>
            <Button
              variant="destructive"
              size="sm"
              className="self-start"
              onClick={async () => {
                await removeServer(s.id);
                setOpen(null);
              }}
            >
              Remove server
            </Button>
          </div>
        ),
      },
    }));

    const addServerBox: Omit<Box, "action"> = {
      key: "mcp:add",
      name: "Custom MCP server",
      direction: "in",
      blurb: "Register any MCP server and your cloud agent gets it before every turn.",
      icon: <TileIcon icon={Server} />,
      active: false,
      tier: TIER.work,
      sortLast: true,
      search: "custom mcp server add tool",
      onAction: () => setAddingServer(true),
    };

    // A coding agent is two integrations wearing one name, so it gets a box
    // per direction with the half that applies.
    const agentBoxes: Omit<Box, "action">[] = (["in", "out"] as const).flatMap((d) =>
      CODING_AGENTS.map((agent) => ({
        key: `agent:${d}:${agent.binary}`,
        name: AGENT_COPY[d].label(agent.name),
        direction: d,
        blurb: AGENT_COPY[d].blurb(agent.name),
        icon: agent.icon,
        active: false,
        tier: TIER.agents,
        search: `${agent.name} ${agent.binary} coding agent`,
        dialog: {
          title: AGENT_COPY[d].title(agent.name),
          description: AGENT_COPY[d].description,
          body: agentDialogBody(),
        },
      })),
    );

    const outputBoxes: Omit<Box, "action">[] = OUTPUT_SURFACES.map((s) => ({
      key: `out:${s.key}`,
      name: s.name,
      direction: "out" as const,
      blurb: s.blurb,
      icon: <TileIcon icon={s.icon} />,
      active: false,
      tier: TIER.work,
      search: `${s.name} ${s.blurb} ${s.keywords}`,
      dialog: { title: s.name, description: s.blurb, body: s.body },
    }));

    // Every box that opens a dialog gets its button built here, so the grid
    // can't sprout a different shape of action per box type.
    const withDialogs: Box[] = [
      ...sourceBoxes,
      browserBox,
      addServerBox,
      ...serverBoxes,
      ...agentBoxes,
      ...outputBoxes,
    ].map((b) => ({
      ...b,
      action: (
        <Button
          size="sm"
          variant="secondary"
          className="self-start"
          onClick={() => (b.onAction ? b.onAction() : setOpen({ ...b, action: null }))}
        >
          {b.actionLabel ?? "Connect"}
        </Button>
      ),
    }));

    return [...withDialogs].sort(
      (a, b) =>
        Number(b.active) - Number(a.active) ||
        a.tier - b.tier ||
        Number(!!a.sortLast) - Number(!!b.sortLast) ||
        a.name.localeCompare(b.name),
    );
  }, [statuses, servers, busy, isConnected, connectNow, removeServer]);

  const matchesQuery = useCallback(
    (b: Box) => {
      const q = query.trim().toLowerCase();
      return q === "" || b.search.toLowerCase().includes(q);
    },
    [query],
  );

  const visible = useMemo(
    () => boxes.filter((b) => b.direction === direction && matchesQuery(b)),
    [boxes, direction, matchesQuery],
  );

  // Only one direction is on screen, so a search that matches nothing here but
  // something in the other half would otherwise read as "no results" when
  // there are results one click away.
  const elsewhere = useMemo(
    () => boxes.filter((b) => b.direction !== direction && matchesQuery(b)).length,
    [boxes, direction, matchesQuery],
  );

  if (loading || !user) return null;

  const connectedCount = boxes.filter((b) => b.direction === direction && b.active).length;

  return (
    <div className="h-full overflow-y-auto">
      <div className="mx-auto flex max-w-5xl flex-col gap-5 px-8 py-7">
        <header>
          <h1 className="font-display text-[22px] font-semibold tracking-tight text-foreground">
            Connect
          </h1>
          <p className="mt-1 max-w-2xl text-sm text-muted-foreground">
            Choose what to add to your Stash, and what can read it.
          </p>
        </header>

        <div className="flex flex-wrap items-center gap-2">
          <Input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Search integrations…"
            aria-label="Search integrations"
            className="h-9 max-w-xs"
          />
          {(["in", "out"] as const).map((d) => (
            <button
              key={d}
              type="button"
              aria-pressed={direction === d}
              onClick={() => setDirection(d)}
              className={cn(
                "rounded-full border px-3 py-1.5 text-[12.5px] font-medium transition-colors",
                direction === d
                  ? d === "in"
                    ? "border-human/40 bg-human/10 text-human"
                    : "border-warning/40 bg-chart-5/15 text-warning"
                  : "border-border bg-surface text-muted-foreground hover:text-foreground",
              )}
            >
              {d === "in" ? "Inputs" : "Outputs"}
              <span className="ml-1.5 text-[11px] opacity-60">
                {boxes.filter((b) => b.direction === d).length}
              </span>
            </button>
          ))}
          {connectedCount > 0 && (
            <span className="ml-auto text-[12.5px] text-muted-foreground">
              {connectedCount} connected
            </span>
          )}
        </div>

        {loadError && (
          <div className="rounded-xl border border-border bg-surface px-4 py-6 text-center text-[13px] text-destructive">
            Couldn&apos;t load integrations: {loadError}
          </div>
        )}

        {statuses === null && !loadError ? (
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
            {Array.from({ length: 9 }, (_, i) => (
              <Skeleton key={i} className="h-[124px] rounded-xl" />
            ))}
          </div>
        ) : (
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
            {visible.map((box) => (
              <IntegrationBox
                key={box.key}
                box={box}
                onOpen={box.dialog ? () => setOpen(box) : undefined}
              />
            ))}
          </div>
        )}

        {statuses !== null && visible.length === 0 && (
          <p className="py-8 text-center text-[13px] text-muted-foreground">
            Nothing matches “{query}” here.
            {elsewhere > 0 && (
              <>
                {" "}
                <button
                  type="button"
                  onClick={() => setDirection(direction === "in" ? "out" : "in")}
                  className="font-medium text-brand-600 hover:underline"
                >
                  {elsewhere} {elsewhere === 1 ? "match" : "matches"} in{" "}
                  {direction === "in" ? "Outputs" : "Inputs"} →
                </button>
              </>
            )}
          </p>
        )}
      </div>

      <Dialog open={open !== null} onOpenChange={(v) => !v && setOpen(null)}>
        <DialogContent>
          <DialogHeader>
            <div className="flex items-start gap-3">
              <span className="mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center [&_img]:h-7 [&_img]:w-7 [&_svg]:h-7 [&_svg]:w-7">
                {open?.icon}
              </span>
              <div className="flex min-w-0 flex-col gap-1">
                <DialogTitle>{open?.dialog?.title}</DialogTitle>
                <DialogDescription>{open?.dialog?.description}</DialogDescription>
              </div>
            </div>
          </DialogHeader>
          {open?.dialog?.body}
          <DialogFooter>
            <Button size="sm" onClick={() => setOpen(null)}>
              Done
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog open={addingServer} onOpenChange={setAddingServer}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Connect an MCP server</DialogTitle>
            <DialogDescription>
              Your cloud agent gets it before every turn, alongside the tools Stash gives it
              natively.
            </DialogDescription>
          </DialogHeader>
          <AddServerForm
            onAdded={() => {
              setAddingServer(false);
              void refreshServers();
            }}
          />
        </DialogContent>
      </Dialog>

      {paywalled && <PaywallModal onClose={() => setPaywalled(false)} />}
    </div>
  );
}
