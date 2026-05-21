"use client";

import { type ReactNode } from "react";
import { ResponsiveContainer } from "recharts";

// 20-step palette used across all admin analytics charts.
export const PALETTE = [
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

export function ChartShell({
  children,
  height = 300,
}: {
  children: ReactNode;
  height?: number;
}) {
  return (
    <div style={{ width: "100%", height }}>
      <ResponsiveContainer>{children as never}</ResponsiveContainer>
    </div>
  );
}

export function ChartCard({
  title,
  children,
  height = 300,
  controls,
}: {
  title: string;
  children: ReactNode;
  height?: number;
  controls?: ReactNode;
}) {
  return (
    <div className="rounded-lg border border-gray-200 bg-white p-5">
      <div className="mb-3 flex items-center justify-between gap-3">
        <h3 className="text-sm font-medium text-gray-700">{title}</h3>
        {controls}
      </div>
      <ChartShell height={height}>{children}</ChartShell>
    </div>
  );
}

export function Stat({
  label,
  value,
}: {
  label: string;
  value: string | number;
}) {
  return (
    <div className="rounded-md border border-gray-200 bg-white p-4">
      <p className="text-xs uppercase tracking-[0.14em] text-gray-400">
        {label}
      </p>
      <p className="mt-1 text-xl font-semibold text-gray-800">
        {typeof value === "number" ? value.toLocaleString() : value}
      </p>
    </div>
  );
}

type ToggleOpt<V extends string> = { value: V; label: string };

export function Toggle<V extends string>({
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

type FocusedTooltipPayloadEntry = {
  dataKey?: string | number;
  name?: string;
  value?: number;
};

export function FocusedTooltip({
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
  cohortSize?: Record<string, number>;
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
      {showSize && cohortSize && cohortSize[name] != null && (
        <div className="text-gray-400">size {cohortSize[name]}</div>
      )}
    </div>
  );
}
