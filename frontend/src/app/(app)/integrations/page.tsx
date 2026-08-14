"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useState, type ReactNode } from "react";
import { useRouter } from "next/navigation";
import { Bot, Globe, Plus, SquareTerminal } from "lucide-react";
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
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import {
  ApiError,
  deleteMcpServer,
  listAgentNames,
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
  /** Setup instructions, for boxes whose action is "Set up". */
  dialog?: { title: string; description: string; body: ReactNode };
  action: ReactNode;
};

function IntegrationBox({ box, onOpen }: { box: Box; onOpen?: () => void }) {
  return (
    <div className="flex flex-col gap-2.5 rounded-xl border border-border bg-surface p-4">
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

/** A lucide glyph in the same tile the brand marks sit in, so a box with no
 *  logo still lines up with one that has. */
function TileIcon({ icon: Icon }: { icon: typeof Bot }) {
  return (
    <span className="flex h-7 w-7 items-center justify-center rounded-md bg-raised">
      <Icon className="h-4 w-4 text-dim" />
    </span>
  );
}

export default function IntegrationsPage() {
  const router = useRouter();
  const { user, loading } = useAuth();
  const [sourceProviders, setSourceProviders] = useState<Set<string>>(new Set());
  const [statuses, setStatuses] = useState<Record<string, IntegrationStatus> | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [agentNames, setAgentNames] = useState<string[]>([]);
  const [servers, setServers] = useState<McpServer[]>([]);
  const [query, setQuery] = useState("");
  const [direction, setDirection] = useState<Direction>("in");
  const [open, setOpen] = useState<Box | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [paywalled, setPaywalled] = useState(false);
  const [addingServer, setAddingServer] = useState(false);

  useBreadcrumbs([{ label: "Integrations" }], "integrations");

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

  // The agent roster is a nice-to-have line, not a gate: it says what is
  // already sending sessions, and the page is complete without it.
  useEffect(() => {
    listAgentNames().then(setAgentNames).catch(() => setAgentNames([]));
  }, []);

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

    const sourceBoxes: Box[] = connectors.map((c) => {
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
        action: connected ? (
          <Button asChild variant="ghost" size="sm" className="self-start px-2">
            <Link href={`/integrations/${c.provider}`}>Manage</Link>
          </Button>
        ) : oauth ? (
          <Button
            size="sm"
            variant="secondary"
            className="self-start"
            disabled={busy === c.provider}
            onClick={() => void connectNow(c)}
          >
            {busy === c.provider ? "Connecting…" : "Connect"}
          </Button>
        ) : (
          <Button asChild size="sm" variant="secondary" className="self-start">
            <Link href={`/integrations/${c.provider}`}>Connect</Link>
          </Button>
        ),
      };
    });

    const browserBox: Box = {
      key: "browser",
      name: "Stash for Chrome",
      direction: "in",
      blurb: "Clip any page or every open tab, import your bookmarks, keep your saves in sync.",
      icon: <TileIcon icon={Globe} />,
      active: false,
      tier: TIER.personal,
      search: "browser chrome extension clip bookmarks tabs",
      action: (
        <Button asChild size="sm" variant="secondary" className="self-start">
          <Link href="/extension">Install</Link>
        </Button>
      ),
    };

    const serverBoxes: Box[] = servers.map((s) => ({
      key: `mcp:${s.id}`,
      name: s.name,
      direction: "in",
      blurb:
        (s.transport === "stdio" ? s.command : s.url) +
        (Object.keys(s.headers).length > 0
          ? ` · headers: ${Object.keys(s.headers).join(", ")}`
          : ""),
      icon: <TileIcon icon={s.transport === "stdio" ? SquareTerminal : Globe} />,
      active: true,
      tier: TIER.work,
      search: `${s.name} mcp server tool ${s.url ?? ""} ${s.command ?? ""}`,
      action: (
        <Button
          variant="ghost"
          size="sm"
          className="self-start px-2"
          onClick={() => void removeServer(s.id)}
        >
          Remove
        </Button>
      ),
    }));

    const addServerBox: Box = {
      key: "mcp:add",
      name: "Custom MCP server",
      direction: "in",
      blurb: "Register any MCP server and your cloud agent gets it before every turn.",
      icon: <TileIcon icon={Plus} />,
      active: false,
      tier: TIER.work,
      sortLast: true,
      search: "custom mcp server add tool",
      action: (
        <Button
          size="sm"
          variant="secondary"
          className="self-start"
          onClick={() => setAddingServer(true)}
        >
          Add
        </Button>
      ),
    };

    // A coding agent is two integrations wearing one name, so it gets a box
    // per direction with the half that applies.
    const agentBoxes = (["in", "out"] as const).flatMap((d) =>
      CODING_AGENTS.map((agent) => ({
        key: `agent:${d}:${agent.binary}`,
        name: agent.name,
        direction: d,
        blurb: AGENT_COPY[d].blurb,
        icon: <TileIcon icon={Bot} />,
        active: false,
        tier: TIER.agents,
        search: `${agent.name} ${agent.binary} coding agent`,
        dialog: {
          title: AGENT_COPY[d].title(agent.name),
          description: AGENT_COPY[d].description,
          body: agentDialogBody(agent, d),
        },
      })),
    );

    const outputBoxes = OUTPUT_SURFACES.map((s) => ({
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

    // Every box whose action is a dialog gets the same button, so the grid
    // doesn't sprout a different verb per box type.
    const withSetup: Box[] = [...agentBoxes, ...outputBoxes].map((b) => ({
      ...b,
      action: (
        <Button size="sm" variant="secondary" className="self-start" onClick={() => setOpen(b as Box)}>
          Set up
        </Button>
      ),
    }));

    return [...sourceBoxes, browserBox, ...serverBoxes, addServerBox, ...withSetup].sort(
      (a, b) =>
        a.tier - b.tier ||
        Number(!!a.sortLast) - Number(!!b.sortLast) ||
        Number(b.active) - Number(a.active) ||
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
            Integrations
          </h1>
          <p className="mt-1 max-w-2xl text-sm text-muted-foreground">
            Everything that flows into Stash, and every way it flows back out to an agent.
            {agentNames.length > 0 && (
              <> {agentNames.length} agent{agentNames.length === 1 ? " is" : "s are"} sending sessions now.</>
            )}
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
            </button>
          ))}
          {connectedCount > 0 && (
            <span className="ml-auto font-mono text-[11.5px] text-muted-foreground">
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
            <DialogTitle>{open?.dialog?.title}</DialogTitle>
            <DialogDescription>{open?.dialog?.description}</DialogDescription>
          </DialogHeader>
          {open?.dialog?.body}
        </DialogContent>
      </Dialog>

      <Dialog open={addingServer} onOpenChange={setAddingServer}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Add an MCP server</DialogTitle>
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
