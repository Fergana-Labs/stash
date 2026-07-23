"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useEffect, useMemo, useState } from "react";
import {
  Area,
  AreaChart,
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Legend,
  Line,
  LineChart,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import {
  ChartCard,
  ChartShell,
  FocusedTooltip,
  PALETTE,
  Stat,
  Toggle,
} from "./_components";

// ---- API payload shapes ----

export type Cohort = {
  cohort_label: string;
  cohort_start: string;
  size: number;
  retention: number[];
  active_users: number[];
  actions: number[];
  avg_cumulative_actions: number[];
};

export type CohortResponse = {
  bucket: "month" | "week" | "rolling_7d";
  mode: "standard" | "future";
  events_filter: "all" | "active";
  max_period: number;
  cohorts: Cohort[];
  totals: { users: number; events: number };
  generated_at: string;
};

type ContentActivityRow = {
  ts: string;
  kind: string;
  via: string;
  count: number;
};
type ContentActivityResponse = {
  days: number;
  totals: {
    reads: { cli: number; ask: number };
    searches: { web: number; cli: number; ask: number };
    listings: { cli: number; ask: number };
  };
  rows: ContentActivityRow[];
  generated_at: string;
};

type SummaryResponse = {
  days: number;
  signups: number;
  onboardings_completed: number;
  active_users: number;
  cli_active_users: number;
  generated_at: string;
};

type FunnelStage = {
  stage: string;
  event_name: string;
  users: number;
  drop_off_pct: number | null;
};

type FunnelResponse = {
  days: number;
  path: string | null;
  stages: FunnelStage[];
};

type PathMixRow = { ts: string; path: string; count: number };
type PathMixResponse = { days: number; bucket: string; rows: PathMixRow[] };

type SurfaceMixRow = { ts: string; surface: string; count: number };
type SurfaceMixResponse = {
  days: number;
  bucket: string;
  rows: SurfaceMixRow[];
};

type TopEventsRow = { event_name: string; total: number; users: number };
type TopEventsResponse = { days: number; rows: TopEventsRow[] };

export type AnalyticsPayload = {
  contentActivity: ContentActivityResponse;
  summary: SummaryResponse;
  funnel: FunnelResponse;
  pathMix: PathMixResponse;
  surfaceMix: SurfaceMixResponse;
  topEvents: TopEventsResponse;
  cohorts: CohortResponse;
};

// ---- Toggle option sets ----

const BUCKET_OPTS = [
  { value: "month", label: "Month" },
  { value: "week", label: "Week" },
  { value: "rolling_7d", label: "Rolling 7-day" },
] as const;

const MODE_OPTS = [
  { value: "standard", label: "Standard" },
  { value: "future", label: "Future" },
] as const;

const FILTER_OPTS = [
  { value: "all", label: "All events" },
  { value: "active", label: "Active events" },
] as const;

const PATH_OPTS = [
  { value: "all", label: "All paths" },
  { value: "migrant", label: "Migrant" },
  { value: "memory", label: "Memory" },
  { value: "sharing", label: "Sharing" },
] as const;

const WINDOW_OPTS = [
  { value: "7", label: "7d" },
  { value: "30", label: "30d" },
  { value: "90", label: "90d" },
] as const;

// ---- Helpers ----

function pivot<R extends { ts: string }>(
  rows: R[],
  keyOf: (r: R) => string,
  valueOf: (r: R) => number,
): { data: Array<Record<string, number | string>>; keys: string[] } {
  const byTs = new Map<string, Record<string, number | string>>();
  const tsOrder: string[] = [];
  const keys = new Set<string>();
  for (const r of rows) {
    const day = r.ts.slice(0, 10);
    if (!byTs.has(day)) {
      byTs.set(day, { label: day });
      tsOrder.push(day);
    }
    const k = keyOf(r);
    keys.add(k);
    byTs.get(day)![k] = ((byTs.get(day)![k] as number) ?? 0) + valueOf(r);
  }
  const keyList = [...keys];
  for (const ts of tsOrder) {
    const row = byTs.get(ts)!;
    for (const k of keyList) {
      if (row[k] == null) row[k] = 0;
    }
  }
  tsOrder.sort();
  return { data: tsOrder.map((ts) => byTs.get(ts)!), keys: keyList };
}

function periodPrefix(bucket: CohortResponse["bucket"]): string {
  if (bucket === "month") return "M";
  if (bucket === "week") return "W";
  return "P";
}

function buildOffsetData(
  cohorts: Cohort[],
  field: "retention" | "avg_cumulative_actions",
  bucket: CohortResponse["bucket"],
  asPercent = false,
) {
  const max = Math.max(0, ...cohorts.map((c) => c[field].length));
  const prefix = periodPrefix(bucket);
  type Row = { label: string; [k: string]: number | string | null };
  return Array.from({ length: max }, (_, p) => {
    const row: Row = { label: `${prefix}${p}` };
    for (const c of cohorts) {
      const v = c[field][p];
      if (v == null) row[c.cohort_label] = null;
      else row[c.cohort_label] = asPercent ? Number((v * 100).toFixed(2)) : v;
    }
    return row;
  });
}

// ---- Top-level client ----

export default function AnalyticsClient({
  data,
  bucket,
  mode,
  eventsFilter,
  funnelPath,
  windowDays,
}: {
  data: AnalyticsPayload;
  bucket: CohortResponse["bucket"];
  mode: CohortResponse["mode"];
  eventsFilter: CohortResponse["events_filter"];
  funnelPath: "all" | "migrant" | "memory" | "sharing";
  windowDays: number;
}) {
  const router = useRouter();
  const params = useSearchParams();
  const setParam = (key: string, value: string) => {
    const next = new URLSearchParams(params.toString());
    if (value === "" || value === "all") next.delete(key);
    else next.set(key, value);
    // scroll: false keeps the user where they were after a toggle refetches
    // server-rendered data — the default would yank them back to the top.
    router.push(`/admin/analytics?${next.toString()}`, { scroll: false });
  };

  return (
    <main className="min-h-screen bg-gray-50 text-gray-800">
      <header className="border-b border-gray-200 bg-white">
        <div className="mx-auto flex h-14 max-w-[1280px] items-center justify-between px-6">
          <div className="flex items-center gap-3">
            <Link href="/" className="text-[15px] font-semibold text-gray-800">
              stash
            </Link>
            <span className="text-xs uppercase tracking-[0.14em] text-gray-400">
              Admin · Analytics
            </span>
          </div>
          <div className="flex items-center gap-4">
            <Link
              href="/admin/skills"
              className="text-sm text-gray-500 hover:text-gray-800"
            >
              Discover Skills →
            </Link>
            <GeneratedAt iso={data.summary.generated_at} />
          </div>
        </div>
      </header>

      <section className="mx-auto max-w-[1280px] px-6 py-8">
        <div className="flex flex-wrap items-end justify-between gap-4">
          <div>
            <h1 className="text-2xl font-semibold text-gray-800">
              Product analytics
            </h1>
            <p className="mt-1 max-w-[640px] text-sm text-gray-500">
              Onboarding funnels, surface mix across web + CLI + agent plugins,
              and engagement cohorts — all from one screen.
            </p>
          </div>
          <Toggle
            label="Window"
            value={String(windowDays)}
            options={WINDOW_OPTS}
            onChange={(v) => setParam("days", v)}
          />
        </div>

        <ContentActivitySection activity={data.contentActivity} />
        <SummarySection summary={data.summary} />
        <FunnelSection
          funnel={data.funnel}
          pathMix={data.pathMix}
          path={funnelPath}
          onPathChange={(v) => setParam("path", v)}
        />
        <SurfaceSection
          surfaceMix={data.surfaceMix}
          topEvents={data.topEvents}
        />
        <CohortsSection
          data={data.cohorts}
          bucket={bucket}
          mode={mode}
          eventsFilter={eventsFilter}
          onChange={setParam}
        />
      </section>
    </main>
  );
}

// Server renders the ISO timestamp as-is; client upgrades to the user's
// locale-formatted version after mount. Splitting the two passes avoids
// the locale/timezone hydration mismatch that triggers React #418 and
// kills event handlers on the whole client tree.
function GeneratedAt({ iso }: { iso: string }) {
  const [pretty, setPretty] = useState<string | null>(null);
  useEffect(() => {
    setPretty(new Date(iso).toLocaleString());
  }, [iso]);
  return (
    <span className="text-[11px] text-gray-400" suppressHydrationWarning>
      generated {pretty ?? iso}
    </span>
  );
}

// ---- Section 0: Content activity (docs read / searches / listings) ----

const ACTIVITY_KINDS = ["reads", "searches", "listings"] as const;

const ACTIVITY_LABELS: Record<(typeof ACTIVITY_KINDS)[number], string> = {
  reads: "Docs read",
  searches: "Searches",
  listings: "Listings",
};

// Web reads/listings are UI noise and aren't counted server-side, so those
// kinds only ever carry cli + ask surfaces. Fixed render order keeps each
// grid column a single source (web last, since only searches carry it).
const SURFACE_ORDER = ["cli", "ask", "web"] as const;

const SURFACE_LABELS: Record<string, string> = {
  web: "Web",
  cli: "CLI",
  ask: "Ask the stash",
};

// Fixed per-kind chart colors: the shared PALETTE is all greens, which made
// listings indistinguishable from reads/searches. Light orange for listings.
const ACTIVITY_COLORS: Record<(typeof ACTIVITY_KINDS)[number], string> = {
  reads: PALETTE[0],
  searches: PALETTE[1],
  listings: "#fdba74",
};

const CHART_SURFACE_OPTS = [
  { value: "all", label: "All" },
  { value: "cli", label: "CLI" },
  { value: "ask", label: "Ask the stash" },
  { value: "web", label: "Web" },
] as const;

function ContentActivitySection({
  activity,
}: {
  activity: ContentActivityResponse;
}) {
  // Chart-only source filter; the stat cards always show every surface.
  const [chartSurface, setChartSurface] = useState("all");

  const chartData = useMemo(() => {
    const rows =
      chartSurface === "all"
        ? activity.rows
        : activity.rows.filter((r) => r.via === chartSurface);
    const { data } = pivot(
      rows,
      (r) => r.kind,
      (r) => r.count,
    );
    // pivot only zero-fills kinds it has seen; a kind with no rows in the
    // window would otherwise vanish from the tooltip instead of reading 0.
    for (const row of data) {
      for (const kind of ACTIVITY_KINDS) {
        if (row[kind] == null) row[kind] = 0;
      }
    }
    return data;
  }, [activity.rows, chartSurface]);

  return (
    <div className="mt-6 space-y-6">
      <h2 className="text-base font-semibold text-gray-800">
        Content activity
      </h2>

      {ACTIVITY_KINDS.map((kind) => {
        const totals: Record<string, number> = activity.totals[kind];
        return (
          <div key={kind} className="grid grid-cols-1 gap-3 sm:grid-cols-3">
            {SURFACE_ORDER.filter((surface) => surface in totals).map(
              (surface) => (
                <Stat
                  key={`${kind}-${surface}`}
                  label={`${ACTIVITY_LABELS[kind]} — ${SURFACE_LABELS[surface]} (${activity.days}d)`}
                  value={totals[surface]}
                />
              ),
            )}
          </div>
        );
      })}

      <ChartCard
        title={`Daily reads, searches & listings — last ${activity.days}d`}
        height={280}
        controls={
          <Toggle
            label=""
            value={chartSurface}
            options={CHART_SURFACE_OPTS}
            onChange={setChartSurface}
          />
        }
      >
        <LineChart data={chartData}>
          <CartesianGrid strokeDasharray="3 3" />
          <XAxis
            dataKey="label"
            tick={{ fontSize: 10 }}
            interval="preserveStartEnd"
          />
          <YAxis tick={{ fontSize: 11 }} allowDecimals={false} />
          <Tooltip />
          <Legend />
          {ACTIVITY_KINDS.map((kind) => (
            <Line
              key={kind}
              // linear, not monotone: smoothed curves imply activity between
              // days that never happened
              type="linear"
              dataKey={kind}
              stroke={ACTIVITY_COLORS[kind]}
              strokeWidth={2}
              dot={false}
              isAnimationActive={false}
            />
          ))}
        </LineChart>
      </ChartCard>
    </div>
  );
}

// ---- Section 1: Summary stat boxes ----

function SummarySection({ summary }: { summary: SummaryResponse }) {
  return (
    <div className="mt-6 grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-4">
      <Stat label={`Signups (${summary.days}d)`} value={summary.signups} />
      <Stat
        label={`Onboardings completed (${summary.days}d)`}
        value={summary.onboardings_completed}
      />
      <Stat
        label={`Active users (${summary.days}d)`}
        value={summary.active_users}
      />
      <Stat
        label={`CLI active users (${summary.days}d)`}
        value={summary.cli_active_users}
      />
    </div>
  );
}

// ---- Section 2: Onboarding funnel + path mix ----

function FunnelSection({
  funnel,
  pathMix,
  path,
  onPathChange,
}: {
  funnel: FunnelResponse;
  pathMix: PathMixResponse;
  path: "all" | "migrant" | "memory" | "sharing";
  onPathChange: (v: string) => void;
}) {
  const funnelData = funnel.stages.map((s) => ({
    label: s.stage,
    users: s.users,
    drop_off:
      s.drop_off_pct == null ? null : Number((s.drop_off_pct * 100).toFixed(1)),
  }));

  const { data: pathMixData, keys: pathKeys } = useMemo(
    () =>
      pivot(
        pathMix.rows,
        (r) => r.path || "unknown",
        (r) => r.count,
      ),
    [pathMix.rows],
  );

  return (
    <div className="mt-8 space-y-6">
      <h2 className="text-base font-semibold text-gray-800">
        Onboarding funnel
      </h2>

      <ChartCard
        title={`Funnel by stage — last ${funnel.days}d`}
        height={260}
        controls={
          <Toggle
            label=""
            value={path}
            options={PATH_OPTS}
            onChange={onPathChange}
          />
        }
      >
        <BarChart data={funnelData} layout="vertical" margin={{ left: 40 }}>
          <CartesianGrid strokeDasharray="3 3" />
          <XAxis type="number" tick={{ fontSize: 11 }} />
          <YAxis
            type="category"
            dataKey="label"
            tick={{ fontSize: 11 }}
            width={120}
          />
          <Tooltip
            content={({ active, payload }) => {
              if (!active || !payload || !payload.length) return null;
              const row = payload[0].payload as (typeof funnelData)[number];
              return (
                <div className="rounded border border-gray-200 bg-white px-3 py-2 text-xs shadow-sm">
                  <div className="font-medium text-gray-700">{row.label}</div>
                  <div className="text-gray-600">
                    {row.users.toLocaleString()} users
                  </div>
                  {row.drop_off != null && (
                    <div className="text-gray-400">
                      drop-off {row.drop_off}%
                    </div>
                  )}
                </div>
              );
            }}
          />
          <Bar dataKey="users" isAnimationActive={false}>
            {funnelData.map((_, i) => (
              <Cell key={i} fill={PALETTE[i % PALETTE.length]} />
            ))}
          </Bar>
        </BarChart>
      </ChartCard>

      <ChartCard title="Path mix over time (daily)" height={260}>
        <AreaChart data={pathMixData}>
          <CartesianGrid strokeDasharray="3 3" />
          <XAxis dataKey="label" tick={{ fontSize: 10 }} interval="preserveStartEnd" />
          <YAxis tick={{ fontSize: 11 }} />
          <Tooltip />
          <Legend />
          {pathKeys.map((k, i) => (
            <Area
              key={k}
              type="monotone"
              dataKey={k}
              stackId="paths"
              stroke={PALETTE[i % PALETTE.length]}
              fill={PALETTE[i % PALETTE.length]}
              fillOpacity={0.6}
              isAnimationActive={false}
            />
          ))}
        </AreaChart>
      </ChartCard>
    </div>
  );
}

// ---- Section 3: Surface mix + top events ----

function SurfaceSection({
  surfaceMix,
  topEvents,
}: {
  surfaceMix: SurfaceMixResponse;
  topEvents: TopEventsResponse;
}) {
  const { data: surfaceData, keys: surfaceKeys } = useMemo(
    () =>
      pivot(
        surfaceMix.rows,
        (r) => r.surface,
        (r) => r.count,
      ),
    [surfaceMix.rows],
  );

  return (
    <div className="mt-10 space-y-6">
      <h2 className="text-base font-semibold text-gray-800">Surface mix</h2>

      <ChartCard
        title={`Activity by surface — last ${surfaceMix.days}d`}
        height={280}
      >
        <AreaChart data={surfaceData}>
          <CartesianGrid strokeDasharray="3 3" />
          <XAxis dataKey="label" tick={{ fontSize: 10 }} interval="preserveStartEnd" />
          <YAxis tick={{ fontSize: 11 }} />
          <Tooltip />
          <Legend />
          {surfaceKeys.map((k, i) => (
            <Area
              key={k}
              type="monotone"
              dataKey={k}
              stackId="surface"
              stroke={PALETTE[i % PALETTE.length]}
              fill={PALETTE[i % PALETTE.length]}
              fillOpacity={0.6}
              isAnimationActive={false}
            />
          ))}
        </AreaChart>
      </ChartCard>

      <div className="rounded-lg border border-gray-200 bg-white p-5">
        <h3 className="mb-3 text-sm font-medium text-gray-700">
          Top events — last {topEvents.days}d
        </h3>
        <table className="w-full text-sm">
          <thead>
            <tr className="text-left text-[11px] uppercase tracking-[0.14em] text-gray-400">
              <th className="py-2 font-medium">Event</th>
              <th className="py-2 text-right font-medium">Total</th>
              <th className="py-2 text-right font-medium">Users</th>
            </tr>
          </thead>
          <tbody>
            {topEvents.rows.map((r) => (
              <tr key={r.event_name} className="border-t border-gray-100">
                <td className="py-2 font-mono text-[12px] text-gray-700">
                  {r.event_name}
                </td>
                <td className="py-2 text-right text-gray-700">
                  {r.total.toLocaleString()}
                </td>
                <td className="py-2 text-right text-gray-700">
                  {r.users.toLocaleString()}
                </td>
              </tr>
            ))}
            {topEvents.rows.length === 0 && (
              <tr>
                <td colSpan={3} className="py-4 text-center text-sm text-gray-400">
                  No events in window
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}

// ---- Section 4: Engagement cohorts (the original 4 charts) ----

function CohortsSection({
  data,
  bucket,
  mode,
  eventsFilter,
  onChange,
}: {
  data: CohortResponse;
  bucket: CohortResponse["bucket"];
  mode: CohortResponse["mode"];
  eventsFilter: CohortResponse["events_filter"];
  onChange: (key: string, value: string) => void;
}) {
  const [hovered, setHovered] = useState<string | null>(null);
  const cohorts = useMemo(() => [...data.cohorts].reverse(), [data.cohorts]);
  const cohortKeys = cohorts.map((c) => c.cohort_label);
  const cohortSize = useMemo(() => {
    const m: Record<string, number> = {};
    for (const c of cohorts) m[c.cohort_label] = c.size;
    return m;
  }, [cohorts]);

  const retentionData = useMemo(
    () => buildOffsetData(cohorts, "retention", bucket, true),
    [cohorts, bucket],
  );
  const cumulativeData = useMemo(
    () => buildOffsetData(cohorts, "avg_cumulative_actions", bucket),
    [cohorts, bucket],
  );

  return (
    <div className="mt-10 space-y-6">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <h2 className="text-base font-semibold text-gray-800">
          Engagement cohorts
        </h2>
        <div className="flex flex-wrap items-end gap-4">
          <Toggle
            label="Bucket"
            value={bucket}
            options={BUCKET_OPTS}
            onChange={(v) => onChange("bucket", v)}
          />
          <Toggle
            label="Events"
            value={eventsFilter}
            options={FILTER_OPTS}
            onChange={(v) => onChange("events_filter", v)}
          />
        </div>
      </div>

      <div className="rounded-lg border border-gray-200 bg-gray-50/50 p-5">
        <div className="mb-4 flex items-center justify-between">
          <h3 className="text-sm font-medium text-gray-700">
            User retention by cohort
          </h3>
          <div className="flex items-center gap-3">
            <Toggle
              label=""
              value={mode}
              options={MODE_OPTS}
              onChange={(v) => onChange("mode", v)}
            />
            <span className="text-xs text-gray-400">
              {mode === "standard"
                ? "Active in that period"
                : "Active in any future period"}
            </span>
          </div>
        </div>
        <ChartShell>
          <LineChart data={retentionData}>
            <CartesianGrid strokeDasharray="3 3" />
            <XAxis dataKey="label" tick={{ fontSize: 9 }} interval={0} />
            <YAxis domain={[0, 100]} unit="%" tick={{ fontSize: 11 }} />
            <Tooltip
              content={
                <FocusedTooltip
                  hovered={hovered}
                  cohortSize={cohortSize}
                  valueFmt={(v) => `${(v as number).toFixed(0)}%`}
                  showSize
                />
              }
            />
            <Legend
              onMouseEnter={(e) => setHovered(String(e.dataKey))}
              onMouseLeave={() => setHovered(null)}
            />
            {cohortKeys.map((k, i) => (
              <Line
                key={k}
                type="monotone"
                dataKey={k}
                stroke={PALETTE[i % PALETTE.length]}
                strokeWidth={hovered === k ? 3 : hovered ? 1 : 2}
                dot={{
                  r: 3,
                  strokeWidth: 0,
                  fill: PALETTE[i % PALETTE.length],
                }}
                activeDot={{ r: 6, strokeWidth: 2, stroke: "#fff" }}
                connectNulls={false}
                isAnimationActive={false}
              />
            ))}
          </LineChart>
        </ChartShell>
      </div>

      <ChartCard
        title="Avg cumulative actions per user by cohort"
        height={260}
      >
        <LineChart data={cumulativeData}>
          <CartesianGrid strokeDasharray="3 3" />
          <XAxis dataKey="label" tick={{ fontSize: 9 }} interval={0} />
          <YAxis tick={{ fontSize: 11 }} />
          <Tooltip
            content={
              <FocusedTooltip
                hovered={hovered}
                cohortSize={cohortSize}
                valueFmt={(v) =>
                  (v as number).toLocaleString(undefined, {
                    maximumFractionDigits: 1,
                  })
                }
                showSize
              />
            }
          />
          <Legend
            onMouseEnter={(e) => setHovered(String(e.dataKey))}
            onMouseLeave={() => setHovered(null)}
          />
          {cohortKeys.map((k, i) => (
            <Line
              key={k}
              type="monotone"
              dataKey={k}
              stroke={PALETTE[i % PALETTE.length]}
              strokeWidth={hovered === k ? 3 : hovered ? 1 : 2}
              dot={{
                r: 3,
                strokeWidth: 0,
                fill: PALETTE[i % PALETTE.length],
              }}
              activeDot={{ r: 6, strokeWidth: 2, stroke: "#fff" }}
              connectNulls={false}
              isAnimationActive={false}
            />
          ))}
        </LineChart>
      </ChartCard>
    </div>
  );
}
