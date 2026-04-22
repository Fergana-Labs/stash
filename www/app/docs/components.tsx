"use client";

import { useState } from "react";

function slugify(children: React.ReactNode) {
  const text = String(children)
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "");
  return text || "section";
}

export function Callout({ children, type = "info" }: { children: React.ReactNode; type?: "info" | "tip" | "warning" }) {
  const styles = {
    info: "border-brand/30 bg-brand/5",
    tip: "border-green-500/30 bg-green-500/5",
    warning: "border-yellow-500/30 bg-yellow-500/5",
  };
  return (
    <div className={`border rounded-2xl px-5 py-4 my-6 ${styles[type]}`}>
      <div className="text-[15px] leading-7 text-dim">{children}</div>
    </div>
  );
}

export function CodeTabs({ tabs }: { tabs: { label: string; code: string }[] }) {
  const [active, setActive] = useState(0);
  return (
    <div className="my-6 rounded-2xl border border-border overflow-hidden bg-surface">
      <div className="flex border-b border-border">
        {tabs.map((tab, i) => (
          <button
            key={tab.label}
            onClick={() => setActive(i)}
            className={`px-4 py-3 text-xs font-medium transition-colors ${
              i === active ? "text-foreground bg-base border-b-2 border-brand" : "text-muted hover:text-foreground"
            }`}
          >
            {tab.label}
          </button>
        ))}
      </div>
      <pre className="bg-base p-5 overflow-x-auto text-sm text-dim font-mono">
        <code>{tabs[active].code}</code>
      </pre>
    </div>
  );
}

export function Code({ children }: { children: React.ReactNode }) {
  return <code className="bg-surface text-brand px-1.5 py-0.5 rounded-md text-[13px] font-mono">{children}</code>;
}

export function CodeBlock({ children }: { children: string }) {
  return (
    <pre className="bg-surface border border-border rounded-2xl p-5 overflow-x-auto text-sm text-dim my-6 font-mono">
      <code>{children}</code>
    </pre>
  );
}

export function H2({ children }: { children: React.ReactNode }) {
  const id = slugify(children);
  return (
    <h2
      id={id}
      data-docs-heading
      data-docs-level="2"
      data-docs-label={String(children)}
      className="scroll-mt-24 text-2xl font-semibold text-foreground mt-12 mb-4 font-display"
    >
      {children}
    </h2>
  );
}

export function H3({ children }: { children: React.ReactNode }) {
  const id = slugify(children);
  return (
    <h3
      id={id}
      data-docs-heading
      data-docs-level="3"
      data-docs-label={String(children)}
      className="scroll-mt-24 text-xl font-semibold text-foreground mt-10 mb-3"
    >
      {children}
    </h3>
  );
}

export function P({ children }: { children: React.ReactNode }) {
  return <p className="text-[15px] text-dim leading-7 mb-4">{children}</p>;
}

export function ParamTable({ params }: { params: { name: string; type: string; desc: string; required?: boolean }[] }) {
  return (
    <div className="my-6 border border-border rounded-2xl overflow-hidden bg-surface">
      <table className="w-full text-sm">
        <thead>
          <tr className="bg-raised">
            <th className="text-left px-4 py-3 text-xs font-medium text-muted uppercase tracking-wider">Parameter</th>
            <th className="text-left px-4 py-3 text-xs font-medium text-muted uppercase tracking-wider">Type</th>
            <th className="text-left px-4 py-3 text-xs font-medium text-muted uppercase tracking-wider">Description</th>
          </tr>
        </thead>
        <tbody>
          {params.map((p) => (
            <tr key={p.name} className="border-t border-border">
              <td className="px-4 py-3 font-mono text-foreground text-xs align-top">
                {p.name}{p.required && <span className="text-red-400 ml-1">*</span>}
              </td>
              <td className="px-4 py-3 text-muted text-xs align-top">{p.type}</td>
              <td className="px-4 py-3 text-dim text-xs leading-6">{p.desc}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export function Title({ children }: { children: React.ReactNode }) {
  const id = slugify(children);
  return (
    <h1
      id={id}
      data-docs-heading
      data-docs-level="1"
      data-docs-label={String(children)}
      className="scroll-mt-24 text-4xl sm:text-5xl font-bold text-foreground font-display tracking-tight mb-4"
    >
      {children}
    </h1>
  );
}

export function Subtitle({ children }: { children: React.ReactNode }) {
  return <p className="text-lg text-dim leading-8 max-w-2xl mb-10">{children}</p>;
}

export function CommandRef({
  command,
  args,
  description,
  params,
}: {
  command: string;
  args?: string;
  description: string;
  params?: { name: string; type: string; desc: string; required?: boolean }[];
}) {
  return (
    <div className="my-5 rounded-xl border border-border overflow-hidden">
      <div className="px-5 py-3 bg-raised/50 border-b border-border">
        <code className="text-[13px] font-mono">
          <span className="font-semibold text-brand">{command}</span>
          {args && <span className="text-muted ml-2">{args}</span>}
        </code>
      </div>
      <div className="px-5 py-4">
        <p className="text-[14px] text-dim leading-6">{description}</p>
        {params && params.length > 0 && (
          <div className="mt-4 pt-4 border-t border-border space-y-3">
            {params.map((p) => (
              <div key={p.name}>
                <div className="flex items-center gap-2 mb-0.5">
                  <code className="text-[12px] font-mono font-medium text-foreground">{p.name}</code>
                  <span className="text-[11px] text-muted">{p.type}</span>
                  {p.required && (
                    <span className="text-[10px] font-bold text-brand uppercase tracking-wider">REQUIRED</span>
                  )}
                </div>
                <p className="text-[12px] text-dim leading-5">{p.desc}</p>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
