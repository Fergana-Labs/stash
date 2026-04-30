"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useMemo, useState, type ReactNode } from "react";
import {
  Area,
  AreaChart,
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

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

const COHORT_COLORS = [
  "#43614a",
  "#6b9e76",
  "#a3d4ae",
  "#2d4a32",
  "#8bb896",
  "#5c8a65",
  "#3a7048",
  "#7ec48a",
  "#4f7656",
  "#96c9a0",
  "#345c3a",
  "#78b284",
  "#569968",
  "#aadbb5",
  "#4a8a54",
  "#618f6a",
  "#87c492",
  "#3e6e46",
  "#72ae7e",
  "#5a9464",
];

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

function periodPrefix(bucket: CohortResponse["bucket"]): string {
  if (bucket === "month") return "M";
  if (bucket === "week") return "W";
  return "P"; // rolling 7-day → P0, P1, ...
}

function calendarLabel(
  cohortStartIso: string,
  periodOffset: number,
  bucket: CohortResponse["bucket"],
): string {
  const d = new Date(cohortStartIso);
  if (bucket === "month") {
    const dt = new Date(Date.UTC(d.getUTCFullYear(), d.getUTCMonth() + periodOffset, 1));
    return `${dt.getUTCFullYear()}-${String(dt.getUTCMonth() + 1).padStart(2, "0")}`;
  }
  // week & rolling_7d: add periodOffset * 7 days
  const dt = new Date(d.getTime() + periodOffset * 7 * 24 * 60 * 60 * 1000);
  if (bucket === "week") {
    const iso = isoWeek(dt);
    return `${iso.year}-W${String(iso.week).padStart(2, "0")}`;
  }
  return `${dt.getUTCFullYear()}-${String(dt.getUTCMonth() + 1).padStart(2, "0")}-${String(dt.getUTCDate()).padStart(2, "0")}`;
}

function isoWeek(d: Date): { year: number; week: number } {
  const t = new Date(Date.UTC(d.getUTCFullYear(), d.getUTCMonth(), d.getUTCDate()));
  const day = t.getUTCDay() || 7;
  t.setUTCDate(t.getUTCDate() + 4 - day);
  const yearStart = new Date(Date.UTC(t.getUTCFullYear(), 0, 1));
  const week = Math.ceil(((t.getTime() - yearStart.getTime()) / 86400000 + 1) / 7);
  return { year: t.getUTCFullYear(), week };
}

type OffsetRow = { label: string; [cohort: string]: number | string | null };
type CalendarRow = { label: string; [cohort: string]: number | string | null };

function buildOffsetData(
  cohorts: Cohort[],
  field: "retention" | "avg_cumulative_actions",
  bucket: CohortResponse["bucket"],
  asPercent = false,
): OffsetRow[] {
  const max = Math.max(0, ...cohorts.map((c) => c[field].length));
  const prefix = periodPrefix(bucket);
  return Array.from({ length: max }, (_, p) => {
    const row: OffsetRow = { label: `${prefix}${p}` };
    for (const c of cohorts) {
      const v = c[field][p];
      if (v == null) row[c.cohort_label] = null;
      else row[c.cohort_label] = asPercent ? Number((v * 100).toFixed(2)) : v;
    }
    return row;
  });
}

function buildCalendarData(
  cohorts: Cohort[],
  field: "actions" | "active_users",
  bucket: CohortResponse["bucket"],
): CalendarRow[] {
  const byLabel = new Map<string, CalendarRow>();
  const labelOrder: string[] = [];
  for (const c of cohorts) {
    for (let p = 0; p < c[field].length; p++) {
      const lbl = calendarLabel(c.cohort_start, p, bucket);
      if (!byLabel.has(lbl)) {
        byLabel.set(lbl, { label: lbl });
        labelOrder.push(lbl);
      }
      byLabel.get(lbl)![c.cohort_label] = c[field][p];
    }
  }
  // Fill missing cells with 0 so stacked areas render contiguously.
  const sorted = labelOrder.sort();
  return sorted.map((lbl) => {
    const row = byLabel.get(lbl)!;
    for (const c of cohorts) {
      if (row[c.cohort_label] == null) row[c.cohort_label] = 0;
    }
    return row;
  });
}

export default function CohortClient({
  data,
  bucket,
  mode,
  eventsFilter,
}: {
  data: CohortResponse;
  bucket: CohortResponse["bucket"];
  mode: CohortResponse["mode"];
  eventsFilter: CohortResponse["events_filter"];
}) {
  const router = useRouter();
  const params = useSearchParams();
  const [hovered, setHovered] = useState<string | null>(null);

  const setParam = (key: string, value: string) => {
    const next = new URLSearchParams(params.toString());
    next.set(key, value);
    router.push(`/admin/cohorts?${next.toString()}`);
  };

  // Cohorts come newest-first from the API; chart everything oldest-first
  // so stacking & legend ordering reads chronologically.
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
  const actionsData = useMemo(
    () => buildCalendarData(cohorts, "actions", bucket),
    [cohorts, bucket],
  );
  const activeData = useMemo(
    () => buildCalendarData(cohorts, "active_users", bucket),
    [cohorts, bucket],
  );

  return (
    <main className="min-h-screen bg-gray-50 text-gray-800">
      <header className="border-b border-gray-200 bg-white">
        <div className="mx-auto flex h-14 max-w-[1280px] items-center justify-between px-6">
          <div className="flex items-center gap-3">
            <Link href="/" className="text-[15px] font-semibold text-gray-800">
              stash
            </Link>
            <span className="text-xs uppercase tracking-[0.14em] text-gray-400">
              Admin · Engagement cohorts
            </span>
          </div>
          <span className="text-[11px] text-gray-400">
            generated {new Date(data.generated_at).toLocaleString()}
          </span>
        </div>
      </header>

      <section className="mx-auto max-w-[1280px] px-6 py-8">
        <div className="flex flex-wrap items-end justify-between gap-4">
          <div>
            <h1 className="text-2xl font-semibold text-gray-800">
              Engagement cohorts
            </h1>
            <p className="mt-1 max-w-[640px] text-sm text-gray-500">
              Users grouped by their first activity. Hover legend entries to
              focus a single cohort across all charts.
            </p>
          </div>
          <div className="flex flex-wrap items-end gap-4">
            <Toggle
              label="Bucket"
              value={bucket}
              options={BUCKET_OPTS}
              onChange={(v) => setParam("bucket", v)}
            />
            <Toggle
              label="Events"
              value={eventsFilter}
              options={FILTER_OPTS}
              onChange={(v) => setParam("events_filter", v)}
            />
          </div>
        </div>

        <div className="mt-6 grid grid-cols-1 gap-3 sm:grid-cols-3">
          <Stat label="Total users" value={data.totals.users.toLocaleString()} />
          <Stat label="Total events" value={data.totals.events.toLocaleString()} />
          <Stat label="Cohorts" value={cohorts.length.toString()} />
        </div>

        <div className="mt-8 space-y-8">
          <div className="rounded-lg border border-gray-200 bg-gray-50/50 p-5">
            <div className="mb-4 flex items-center justify-between">
              <h3 className="text-sm font-medium text-gray-700">
                User Retention by Cohort
              </h3>
              <div className="flex items-center gap-3">
                <Toggle
                  label=""
                  value={mode}
                  options={MODE_OPTS}
                  onChange={(v) => setParam("mode", v)}
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
                    stroke={COHORT_COLORS[i % COHORT_COLORS.length]}
                    strokeWidth={
                      hovered === k ? 3 : hovered ? 1 : 2
                    }
                    dot={{
                      r: 3,
                      strokeWidth: 0,
                      fill: COHORT_COLORS[i % COHORT_COLORS.length],
                    }}
                    activeDot={{ r: 6, strokeWidth: 2, stroke: "#fff" }}
                    connectNulls={false}
                    isAnimationActive={false}
                  />
                ))}
              </LineChart>
            </ChartShell>
          </div>

          <ChartCard title="Total Actions by Cohort">
            <AreaChart data={actionsData}>
              <CartesianGrid strokeDasharray="3 3" />
              <XAxis dataKey="label" tick={{ fontSize: 9 }} interval={0} />
              <YAxis tick={{ fontSize: 11 }} />
              <Tooltip
                content={
                  <FocusedTooltip
                    hovered={hovered}
                    cohortSize={cohortSize}
                    valueFmt={(v) => (v as number).toLocaleString()}
                  />
                }
              />
              <Legend
                onMouseEnter={(e) => setHovered(String(e.dataKey))}
                onMouseLeave={() => setHovered(null)}
              />
              {cohortKeys.map((k, i) => (
                <Area
                  key={k}
                  type="monotone"
                  dataKey={k}
                  stackId="stack"
                  stroke={COHORT_COLORS[i % COHORT_COLORS.length]}
                  fill={COHORT_COLORS[i % COHORT_COLORS.length]}
                  fillOpacity={hovered === k ? 0.85 : hovered ? 0.25 : 0.6}
                  isAnimationActive={false}
                />
              ))}
            </AreaChart>
          </ChartCard>

          <ChartCard title="Active Users by Cohort">
            <AreaChart data={activeData}>
              <CartesianGrid strokeDasharray="3 3" />
              <XAxis dataKey="label" tick={{ fontSize: 9 }} interval={0} />
              <YAxis tick={{ fontSize: 11 }} />
              <Tooltip
                content={
                  <FocusedTooltip
                    hovered={hovered}
                    cohortSize={cohortSize}
                    valueFmt={(v) => (v as number).toLocaleString()}
                  />
                }
              />
              <Legend
                onMouseEnter={(e) => setHovered(String(e.dataKey))}
                onMouseLeave={() => setHovered(null)}
              />
              {cohortKeys.map((k, i) => (
                <Area
                  key={k}
                  type="monotone"
                  dataKey={k}
                  stackId="stack"
                  stroke={COHORT_COLORS[i % COHORT_COLORS.length]}
                  fill={COHORT_COLORS[i % COHORT_COLORS.length]}
                  fillOpacity={hovered === k ? 0.85 : hovered ? 0.25 : 0.6}
                  isAnimationActive={false}
                />
              ))}
            </AreaChart>
          </ChartCard>

          <ChartCard
            title="Avg Cumulative Actions per User by Cohort"
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
                    valueFmt={(v) => (v as number).toLocaleString(undefined, { maximumFractionDigits: 1 })}
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
                  stroke={COHORT_COLORS[i % COHORT_COLORS.length]}
                  strokeWidth={hovered === k ? 3 : hovered ? 1 : 2}
                  dot={{
                    r: 3,
                    strokeWidth: 0,
                    fill: COHORT_COLORS[i % COHORT_COLORS.length],
                  }}
                  activeDot={{ r: 6, strokeWidth: 2, stroke: "#fff" }}
                  connectNulls={false}
                  isAnimationActive={false}
                />
              ))}
            </LineChart>
          </ChartCard>
        </div>
      </section>
    </main>
  );
}

function ChartShell({ children, height = 300 }: { children: ReactNode; height?: number }) {
  return (
    <div style={{ width: "100%", height }}>
      <ResponsiveContainer>{children as never}</ResponsiveContainer>
    </div>
  );
}

function ChartCard({
  title,
  children,
  height = 300,
}: {
  title: string;
  children: ReactNode;
  height?: number;
}) {
  return (
    <div className="rounded-lg border border-gray-200 bg-white p-5">
      <h3 className="mb-3 text-sm font-medium text-gray-700">{title}</h3>
      <ChartShell height={height}>{children}</ChartShell>
    </div>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-md border border-gray-200 bg-white p-4">
      <p className="text-xs uppercase tracking-[0.14em] text-gray-400">
        {label}
      </p>
      <p className="mt-1 text-xl font-semibold text-gray-800">{value}</p>
    </div>
  );
}

type FocusedTooltipPayloadEntry = { dataKey?: string | number; name?: string; value?: number };

function FocusedTooltip({
  active,
  payload,
  label,
  hovered,
  cohortSize,
  valueFmt,
  showSize,
}: {
  active?: boolean;
  payload?: FocusedTooltipPayloadEntry[];
  label?: string;
  hovered: string | null;
  cohortSize: Record<string, number>;
  valueFmt: (v: number) => string;
  showSize?: boolean;
}) {
  if (!active || !payload || payload.length === 0) return null;
  const item = hovered
    ? payload.find((p) => String(p.dataKey) === hovered)
    : payload[0];
  if (!item) return null;
  const name = String(item.dataKey ?? item.name ?? "");
  return (
    <div className="rounded border border-gray-200 bg-white px-3 py-2 text-xs shadow-sm">
      <div className="font-medium text-gray-700">{label}</div>
      <div className="mt-0.5 text-gray-600">
        {name}: {item.value != null ? valueFmt(item.value) : "—"}
      </div>
      {showSize && cohortSize[name] != null && (
        <div className="text-gray-400">size {cohortSize[name]}</div>
      )}
    </div>
  );
}

type ToggleOpt<V extends string> = { value: V; label: string };

function Toggle<V extends string>({
  label,
  value,
  options,
  onChange,
}: {
  label: string;
  value: V;
  options: readonly ToggleOpt<V>[];
  onChange: (v: V) => void;
}) {
  return (
    <div>
      {label && (
        <p className="mb-1 text-[10px] font-medium uppercase tracking-[0.14em] text-gray-400">
          {label}
        </p>
      )}
      <div className="inline-flex overflow-hidden rounded-md border border-gray-300 bg-white">
        {options.map((opt) => {
          const isActive = opt.value === value;
          return (
            <button
              key={opt.value}
              type="button"
              onClick={() => onChange(opt.value)}
              className={
                "px-3 py-1.5 text-xs transition " +
                (isActive
                  ? "bg-[#43614a] text-white"
                  : "text-gray-700 hover:bg-gray-50")
              }
            >
              {opt.label}
            </button>
          );
        })}
      </div>
    </div>
  );
}
