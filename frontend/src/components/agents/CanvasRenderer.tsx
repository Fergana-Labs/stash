"use client";

import { useState } from "react";

import type { CanvasBlock } from "@/lib/types";

// Renders an agent-generated canvas: an ordered list of UI blocks. The block
// catalog here is the contract shared with the backend agent tools (see
// backend/services/agent_runtime.py _CANVAS_BLOCKS_DOC). Unknown block types
// degrade to a small placeholder rather than throwing — the agent may ship a
// block type ahead of the renderer.
//
// `onAction` is the chat→canvas→chat loop: buttons and form submits send a
// message back to the agent so a rendered UI can drive the next turn.
export default function CanvasRenderer({
  blocks,
  onAction,
}: {
  blocks: CanvasBlock[];
  onAction: (message: string) => void;
}) {
  return (
    <div className="space-y-4">
      {blocks.map((block, i) => (
        <Block key={i} block={block} onAction={onAction} />
      ))}
    </div>
  );
}

function Block({
  block,
  onAction,
}: {
  block: CanvasBlock;
  onAction: (message: string) => void;
}) {
  switch (block.type) {
    case "heading":
      return <Heading block={block} />;
    case "text":
      return (
        <p className="text-[13.5px] leading-6 whitespace-pre-wrap text-foreground">
          {str(block.text)}
        </p>
      );
    case "stat":
      return <StatCard label={str(block.label)} value={str(block.value)} delta={optStr(block.delta)} />;
    case "stats":
      return <Stats block={block} />;
    case "card":
      return <Card block={block} />;
    case "table":
      return <DataTable block={block} />;
    case "list":
      return <BlockList block={block} />;
    case "chart":
      return <Chart block={block} />;
    case "form":
      return <Form block={block} onAction={onAction} />;
    case "button":
      return (
        <button
          type="button"
          onClick={() => onAction(str(block.message) || str(block.label))}
          className="cursor-pointer rounded-md bg-brand px-4 py-2 text-[13px] font-medium text-white hover:bg-brand-hover"
        >
          {str(block.label) || "Continue"}
        </button>
      );
    case "divider":
      return <hr className="border-border" />;
    case "html":
      return <HtmlBlock block={block} />;
    default:
      return (
        <div className="rounded-md border border-dashed border-border px-3 py-2 text-[12px] text-muted">
          Unsupported block: {block.type}
        </div>
      );
  }
}

function Heading({ block }: { block: CanvasBlock }) {
  const level = typeof block.level === "number" ? block.level : 2;
  const cls =
    level === 1
      ? "text-[20px] font-semibold"
      : level === 3
        ? "text-[14px] font-semibold"
        : "text-[16px] font-semibold";
  return <div className={`${cls} text-foreground`}>{str(block.text)}</div>;
}

function StatCard({ label, value, delta }: { label: string; value: string; delta?: string }) {
  const up = delta?.trim().startsWith("+");
  const down = delta?.trim().startsWith("-");
  return (
    <div className="flex-1 rounded-lg border border-border bg-surface px-4 py-3">
      <div className="text-[11.5px] font-medium tracking-wide text-muted uppercase">{label}</div>
      <div className="mt-1 text-[22px] font-semibold text-foreground">{value}</div>
      {delta && (
        <div
          className={
            "mt-0.5 text-[12px] " +
            (up ? "text-success" : down ? "text-error" : "text-dim")
          }
        >
          {delta}
        </div>
      )}
    </div>
  );
}

function Stats({ block }: { block: CanvasBlock }) {
  const items = Array.isArray(block.items) ? (block.items as Record<string, unknown>[]) : [];
  return (
    <div className="flex flex-wrap gap-3">
      {items.map((it, i) => (
        <StatCard key={i} label={str(it.label)} value={str(it.value)} delta={optStr(it.delta)} />
      ))}
    </div>
  );
}

function Card({ block }: { block: CanvasBlock }) {
  return (
    <div className="rounded-lg border border-border bg-surface p-4">
      {Boolean(block.title) && (
        <div className="mb-1.5 text-[14px] font-semibold text-foreground">{str(block.title)}</div>
      )}
      <div className="text-[13px] leading-6 whitespace-pre-wrap text-dim">{str(block.body)}</div>
    </div>
  );
}

function DataTable({ block }: { block: CanvasBlock }) {
  const columns = Array.isArray(block.columns) ? (block.columns as unknown[]).map(str) : [];
  const rows = Array.isArray(block.rows) ? (block.rows as unknown[][]) : [];
  return (
    <div className="overflow-x-auto rounded-lg border border-border">
      <table className="w-full border-collapse text-[12.5px]">
        <thead>
          <tr className="bg-surface">
            {columns.map((c, i) => (
              <th
                key={i}
                className="border-b border-border px-3 py-2 text-left font-semibold text-foreground"
              >
                {c}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, r) => (
            <tr key={r} className="even:bg-surface/50">
              {(Array.isArray(row) ? row : [row]).map((cell, c) => (
                <td key={c} className="border-b border-border-subtle px-3 py-2 text-dim">
                  {str(cell)}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function BlockList({ block }: { block: CanvasBlock }) {
  const items = Array.isArray(block.items) ? (block.items as unknown[]).map(str) : [];
  const cls = "ml-5 space-y-1 text-[13px] leading-6 text-foreground";
  if (block.ordered) {
    return (
      <ol className={`list-decimal ${cls}`}>
        {items.map((it, i) => (
          <li key={i}>{it}</li>
        ))}
      </ol>
    );
  }
  return (
    <ul className={`list-disc ${cls}`}>
      {items.map((it, i) => (
        <li key={i}>{it}</li>
      ))}
    </ul>
  );
}

function Chart({ block }: { block: CanvasBlock }) {
  const data = Array.isArray(block.data) ? (block.data as Record<string, unknown>[]) : [];
  const points = data
    .map((d) => ({ label: str(d.label), value: Number(d.value) }))
    .filter((d) => Number.isFinite(d.value));
  const max = points.reduce((m, p) => Math.max(m, p.value), 0) || 1;

  return (
    <div className="rounded-lg border border-border bg-surface p-4">
      {Boolean(block.title) && (
        <div className="mb-3 text-[14px] font-semibold text-foreground">{str(block.title)}</div>
      )}
      {block.chartType === "line" ? (
        <LineChart points={points} max={max} />
      ) : (
        <div className="space-y-2">
          {points.map((p, i) => (
            <div key={i} className="flex items-center gap-2">
              <div className="w-28 shrink-0 truncate text-[12px] text-dim">{p.label}</div>
              <div className="h-4 flex-1 overflow-hidden rounded bg-raised">
                <div
                  className="h-full rounded bg-brand"
                  style={{ width: `${Math.max(2, (p.value / max) * 100)}%` }}
                />
              </div>
              <div className="w-14 shrink-0 text-right text-[12px] tabular-nums text-foreground">
                {p.value}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function LineChart({ points, max }: { points: { label: string; value: number }[]; max: number }) {
  if (points.length === 0) return null;
  const w = 100;
  const h = 40;
  const step = points.length > 1 ? w / (points.length - 1) : 0;
  const coords = points.map((p, i) => `${i * step},${h - (p.value / max) * h}`).join(" ");
  return (
    <div>
      <svg viewBox={`0 0 ${w} ${h}`} preserveAspectRatio="none" className="h-32 w-full">
        <polyline
          points={coords}
          fill="none"
          stroke="var(--color-brand)"
          strokeWidth={1.5}
          vectorEffect="non-scaling-stroke"
        />
      </svg>
      <div className="mt-1 flex justify-between text-[11px] text-muted">
        {points.map((p, i) => (
          <span key={i} className="truncate">
            {p.label}
          </span>
        ))}
      </div>
    </div>
  );
}

type FormField = { name: string; label?: string; type?: string; options?: string[] };

function Form({ block, onAction }: { block: CanvasBlock; onAction: (message: string) => void }) {
  const fields = Array.isArray(block.fields) ? (block.fields as FormField[]) : [];
  const [values, setValues] = useState<Record<string, string>>({});
  const set = (name: string, v: string) => setValues((prev) => ({ ...prev, [name]: v }));

  function submit() {
    const parts = fields.map((f) => `${f.label || f.name}: ${values[f.name] ?? ""}`);
    const title = block.title ? str(block.title) : "Form";
    onAction(`${title} submitted — ${parts.join("; ")}`);
  }

  return (
    <div className="rounded-lg border border-border bg-surface p-4">
      {Boolean(block.title) && (
        <div className="mb-3 text-[14px] font-semibold text-foreground">{str(block.title)}</div>
      )}
      <div className="space-y-3">
        {fields.map((f) => (
          <label key={f.name} className="block">
            <span className="mb-1 block text-[12px] font-medium text-dim">{f.label || f.name}</span>
            {f.type === "textarea" ? (
              <textarea
                rows={3}
                value={values[f.name] ?? ""}
                onChange={(e) => set(f.name, e.target.value)}
                className="w-full resize-none rounded-md border border-border bg-base px-3 py-2 text-[13px] text-foreground focus:border-brand focus:outline-none"
              />
            ) : f.type === "select" ? (
              <select
                value={values[f.name] ?? ""}
                onChange={(e) => set(f.name, e.target.value)}
                className="w-full rounded-md border border-border bg-base px-3 py-2 text-[13px] text-foreground focus:border-brand focus:outline-none"
              >
                <option value="">Select…</option>
                {(f.options ?? []).map((o) => (
                  <option key={o} value={o}>
                    {o}
                  </option>
                ))}
              </select>
            ) : (
              <input
                type="text"
                value={values[f.name] ?? ""}
                onChange={(e) => set(f.name, e.target.value)}
                className="w-full rounded-md border border-border bg-base px-3 py-2 text-[13px] text-foreground focus:border-brand focus:outline-none"
              />
            )}
          </label>
        ))}
      </div>
      <button
        type="button"
        onClick={submit}
        className="mt-4 cursor-pointer rounded-md bg-brand px-4 py-2 text-[13px] font-medium text-white hover:bg-brand-hover"
      >
        {str(block.submitLabel) || "Submit"}
      </button>
    </div>
  );
}

function HtmlBlock({ block }: { block: CanvasBlock }) {
  const height = typeof block.height === "number" ? block.height : 360;
  // Sandboxed, null-origin iframe: agent HTML can run scripts but can't reach
  // our app, cookies, or storage. The wrapper gives it a sane base style.
  const doc = `<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><style>body{margin:0;padding:16px;font-family:ui-sans-serif,system-ui,-apple-system,sans-serif;color:#111;background:#fff}</style></head><body>${str(block.html)}</body></html>`;
  return (
    <iframe
      title="canvas-html"
      sandbox="allow-scripts"
      srcDoc={doc}
      className="w-full rounded-lg border border-border bg-white"
      style={{ height }}
    />
  );
}

function str(v: unknown): string {
  if (v === null || v === undefined) return "";
  if (typeof v === "string") return v;
  return String(v);
}

function optStr(v: unknown): string | undefined {
  return v === null || v === undefined || v === "" ? undefined : str(v);
}
