"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { Globe } from "lucide-react";
import { toast } from "sonner";

import { useBreadcrumbs } from "@/components/BreadcrumbContext";
import { useAuth } from "@/hooks/useAuth";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { ApiError, listAgentNames, listSources, type Source } from "@/lib/api";
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
import CodingAgents, { CODING_AGENTS } from "@/components/integrations/CodingAgents";
import McpServers from "@/components/integrations/McpServers";
import OutputSurfaces, { OUTPUT_SURFACES } from "@/components/integrations/OutputSurfaces";
import PaywallModal from "@/components/PaywallModal";
import { cn } from "@/lib/utils";

// Direction is the page's first distinction: what puts content INTO the stash,
// and what reads it back OUT. "MCP" means opposite things on the two sides —
// servers Stash calls (in) versus Stash as a server agents call (out) — so
// neither section is allowed to be called just "MCP".
type Direction = "in" | "out";

type Category = "sources" | "browser" | "tools" | "access" | "agents";

const CATEGORIES: {
  key: Category;
  direction: Direction | "both";
  label: string;
  blurb: string;
}[] = [
  {
    key: "sources",
    direction: "in",
    label: "Sources",
    blurb: "Connect an account and everything in it becomes searchable by every agent you point at Stash.",
  },
  {
    key: "browser",
    direction: "in",
    label: "Browser",
    blurb: "Clip any page, import your bookmarks, and sync what you save on X and Instagram.",
  },
  {
    key: "tools",
    direction: "in",
    label: "Tools your agent can call",
    blurb: "MCP servers you register here are handed to your cloud agent, on top of everything Stash gives it natively.",
  },
  {
    key: "access",
    direction: "out",
    label: "Connect an agent",
    blurb: "MCP, the CLI, and the HTTP API — how an agent or a script reads what you've collected.",
  },
  {
    key: "agents",
    direction: "both",
    label: "Coding agents",
    blurb: "The one surface that runs both ways: their transcripts land in your stash, and they read the rest of it while they work.",
  },
];

/** One connector, as a card: what it is, what connecting gets you, and the
 *  action. OAuth providers connect in place; the rest route to their page,
 *  which holds the credential form or the extension install. */
function ConnectorCard({
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
    <div className="flex flex-col gap-2.5 rounded-xl border border-border bg-surface p-4">
      <div className="flex items-center gap-2.5">
        <span className="flex h-7 w-7 shrink-0 items-center justify-center [&_img]:h-6 [&_img]:w-6 [&_svg]:h-6 [&_svg]:w-6">
          {connectorIcon(connector.provider)}
        </span>
        <Link
          href={`/integrations/${connector.provider}`}
          className="truncate text-[14px] font-medium text-foreground hover:underline"
        >
          {connector.label}
        </Link>
        {connected && (
          <span className="ml-auto flex items-center gap-1.5 rounded-full border border-border bg-base px-2 py-0.5 text-[11px] font-medium text-muted-foreground">
            <span className="h-1.5 w-1.5 rounded-full bg-success" />
            Connected
          </span>
        )}
      </div>

      <p className="min-h-[34px] text-[12.5px] leading-snug text-muted-foreground">
        {connector.blurb}
      </p>

      {connected ? (
        <Button asChild variant="ghost" size="sm" className="self-start px-2">
          <Link href={`/integrations/${connector.provider}`}>Manage</Link>
        </Button>
      ) : onOauthConnect ? (
        <Button size="sm" variant="secondary" className="self-start" disabled={busy} onClick={onOauthConnect}>
          {busy ? "Connecting…" : "Connect"}
        </Button>
      ) : (
        <Button asChild size="sm" variant="secondary" className="self-start">
          <Link href={`/integrations/${connector.provider}`}>Connect</Link>
        </Button>
      )}
    </div>
  );
}

/** Every source connector, connected ones first so the page answers "what do
 *  I already have?" before "what could I add?". */
function SourcesGrid({
  connectors,
  statuses,
  onConnected,
}: {
  connectors: Connector[];
  statuses: Record<string, IntegrationStatus>;
  onConnected: (c: Connector) => boolean;
}) {
  const [busy, setBusy] = useState<string | null>(null);
  const [paywalled, setPaywalled] = useState(false);

  // Straight to the consent screen; the OAuth flow returns to /integrations,
  // where the card reads Connected. No successful-return path resets `busy` —
  // the whole page navigates away.
  async function connectNow(connector: Connector) {
    setBusy(connector.provider);
    try {
      await startConnect(connector.provider, "/integrations");
    } catch (e) {
      if (e instanceof ApiError && e.status === 402) setPaywalled(true);
      else toast.error(e instanceof Error ? e.message : "Could not start connection");
      setBusy(null);
    }
  }

  const sorted = [...connectors].sort(
    (a, b) => Number(onConnected(b)) - Number(onConnected(a)) || a.label.localeCompare(b.label),
  );

  return (
    <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
      {sorted.map((c) => {
        const status = statuses[c.provider];
        const oauth =
          c.kind !== "extension" && status?.auth_kind !== "api_key" && !status?.disabled_reason;
        return (
          <ConnectorCard
            key={c.provider}
            connector={c}
            connected={onConnected(c)}
            busy={busy === c.provider}
            onOauthConnect={oauth ? () => void connectNow(c) : null}
          />
        );
      })}
      {paywalled && <PaywallModal onClose={() => setPaywalled(false)} />}
    </div>
  );
}

/** A direction badge — the same mark on the segmented control, the section
 *  headings, and the one category that carries both. */
function DirectionBadge({ direction }: { direction: Direction | "both" }) {
  const label = direction === "in" ? "→ IN" : direction === "out" ? "OUT →" : "⇄ BOTH";
  return (
    <span
      className={cn(
        "rounded-full px-2 py-0.5 font-mono text-[10.5px] font-semibold leading-normal",
        direction === "in" && "bg-human/10 text-human",
        direction === "out" && "bg-chart-5/15 text-warning",
        direction === "both" && "bg-brand-500/10 text-brand-600",
      )}
    >
      {label}
    </span>
  );
}

function Section({
  category,
  count,
  children,
}: {
  category: (typeof CATEGORIES)[number];
  count: number | null;
  children: React.ReactNode;
}) {
  return (
    <section id={category.key}>
      <div className="flex items-center gap-2">
        <h2 className="font-display text-[16px] font-semibold text-foreground">{category.label}</h2>
        {count !== null && (
          <span className="font-mono text-[12px] text-muted-foreground">{count}</span>
        )}
        <DirectionBadge direction={category.direction} />
      </div>
      <p className="mt-0.5 max-w-2xl text-[13px] text-muted-foreground">{category.blurb}</p>
      <div className="mt-4">{children}</div>
    </section>
  );
}

const cat = (key: Category) => CATEGORIES.find((c) => c.key === key)!;

export default function IntegrationsPage() {
  const router = useRouter();
  const { user, loading } = useAuth();
  const [sourceProviders, setSourceProviders] = useState<Set<string>>(new Set());
  const [statuses, setStatuses] = useState<Record<string, IntegrationStatus> | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [agentNames, setAgentNames] = useState<string[]>([]);
  const [mcpCount, setMcpCount] = useState(0);
  const [direction, setDirection] = useState<Direction>("in");
  const [filter, setFilter] = useState<Category | "all">("all");

  useBreadcrumbs([{ label: "Integrations" }], "integrations");

  useEffect(() => {
    if (!loading && !user) router.push("/login");
  }, [user, loading, router]);

  // Both calls decide what a card says — statuses which cards exist, sources
  // whether an extension card reads Connected — so either one failing makes
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

  if (loading || !user) return null;

  // The server omits providers this user may not use (customer-specific
  // integrations like Heavi) — extension connectors are always available.
  const available = statuses
    ? CONNECTORS.filter((c) => c.kind === "extension" || c.provider in statuses)
    : [];
  const connectedCount = available.filter(isConnected).length;

  const counts: Record<Category, number> = {
    sources: available.length,
    browser: 1,
    tools: mcpCount,
    access: OUTPUT_SURFACES.length,
    agents: CODING_AGENTS.length,
  };

  // A category belongs to the open direction if it points that way, or if it
  // runs both ways — coding agents genuinely do, so they appear under each.
  const inDirection = CATEGORIES.filter(
    (c) => c.direction === direction || c.direction === "both",
  );

  // The sub-filter is scoped to the open direction, so switching direction
  // resets it rather than leaving a filter selected that no longer exists.
  const shows = (c: Category) =>
    inDirection.some((cat) => cat.key === c) && (filter === "all" || filter === c);

  function openDirection(next: Direction) {
    setDirection(next);
    setFilter("all");
  }

  return (
    <div className="h-full overflow-y-auto">
      <div className="mx-auto flex max-w-5xl flex-col gap-8 px-8 py-7">
        <header>
          <h1 className="font-display text-[22px] font-semibold tracking-tight text-foreground">
            Integrations
          </h1>
          <p className="mt-1 max-w-2xl text-sm text-muted-foreground">
            The one place to connect everything to Stash. Everything that flows in, and every way
            it flows back out to an agent.
          </p>
          {statuses && (
            <p className="mt-2.5 font-mono text-[12px] text-muted-foreground">
              {connectedCount} of {available.length} sources connected
              {mcpCount > 0 && ` · ${mcpCount} MCP server${mcpCount === 1 ? "" : "s"}`}
              {agentNames.length > 0 &&
                ` · ${agentNames.length} agent${agentNames.length === 1 ? "" : "s"} sending sessions`}
            </p>
          )}
        </header>

        <div className="flex flex-col gap-3">
          {/* Direction is the primary choice; categories nest under whichever
              half is open. */}
          <div className="flex w-full max-w-md overflow-hidden rounded-xl border border-border" role="tablist">
            {(["in", "out"] as const).map((d) => (
              <button
                key={d}
                type="button"
                role="tab"
                aria-selected={direction === d}
                onClick={() => openDirection(d)}
                className={cn(
                  "flex flex-1 items-center justify-center gap-2 px-4 py-2.5 text-[13px] font-semibold transition-colors",
                  d === "out" && "border-l border-border",
                  direction === d
                    ? d === "in"
                      ? "bg-human/10 text-human"
                      : "bg-chart-5/15 text-warning"
                    : "bg-surface text-muted-foreground hover:text-foreground",
                )}
              >
                <span className="font-mono text-[12px]">{d === "in" ? "→" : ""}</span>
                {d === "in" ? "Flowing in" : "Flowing out"}
                <span className="font-mono text-[12px]">{d === "out" ? "→" : ""}</span>
              </button>
            ))}
          </div>

          <p className="text-[12.5px] text-muted-foreground">
            {direction === "in"
              ? "What puts content into your stash."
              : "How agents and scripts read what's in it."}
          </p>

          <div className="flex flex-wrap gap-1.5">
            {(["all", ...inDirection.map((c) => c.key)] as (Category | "all")[]).map((key) => {
              const label =
                key === "all" ? "All" : CATEGORIES.find((c) => c.key === key)!.label;
              const count =
                key === "all"
                  ? inDirection.reduce((sum, c) => sum + counts[c.key], 0)
                  : counts[key as Category];
              return (
                <button
                  key={key}
                  type="button"
                  aria-pressed={filter === key}
                  onClick={() => setFilter(key)}
                  className={cn(
                    "flex items-center gap-1.5 rounded-full border px-3 py-1 text-[12.5px] font-medium transition-colors",
                    filter === key
                      ? "border-brand-500 bg-brand-500/10 text-brand-600"
                      : "border-border bg-surface text-muted-foreground hover:text-foreground",
                  )}
                >
                  {label}
                  <span className="font-mono text-[11px] opacity-70">{count}</span>
                </button>
              );
            })}
          </div>
        </div>

        {loadError && (
          <div className="rounded-xl border border-border bg-surface px-4 py-6 text-center text-[13px] text-destructive">
            Couldn&apos;t load integrations: {loadError}
          </div>
        )}

        {shows("sources") && !loadError && (
          <Section category={cat("sources")} count={counts.sources}>
            {statuses === null ? (
              <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
                {Array.from({ length: 6 }, (_, i) => (
                  <Skeleton key={i} className="h-[124px] rounded-xl" />
                ))}
              </div>
            ) : (
              <SourcesGrid
                connectors={available}
                statuses={statuses}
                onConnected={isConnected}
              />
            )}
          </Section>
        )}

        {shows("browser") && (
          <Section category={cat("browser")} count={counts.browser}>
            <Link
              href="/extension"
              className="flex items-start gap-3 rounded-xl border border-border bg-surface p-4 transition-colors hover:bg-raised sm:max-w-md"
            >
              <Globe className="mt-0.5 h-6 w-6 shrink-0 text-muted-foreground" />
              <span className="flex flex-col gap-1">
                <span className="text-[14px] font-medium text-foreground">Stash for Chrome</span>
                <span className="text-[12.5px] leading-snug text-muted-foreground">
                  Clip any page or every open tab, import your bookmarks, and keep your X and
                  Instagram saves in sync.
                </span>
              </span>
            </Link>
          </Section>
        )}

        {shows("tools") && (
          <Section category={cat("tools")} count={counts.tools}>
            <McpServers onCountChange={setMcpCount} />
          </Section>
        )}

        {shows("access") && (
          <Section category={cat("access")} count={counts.access}>
            <OutputSurfaces />
          </Section>
        )}

        {shows("agents") && (
          <Section category={cat("agents")} count={counts.agents}>
            <CodingAgents agentNames={agentNames} />
          </Section>
        )}

      </div>
    </div>
  );
}
