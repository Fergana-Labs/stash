"use client";

import { useState } from "react";

export function Callout({ children, type = "info" }: { children: React.ReactNode; type?: "info" | "tip" | "warning" }) {
  const styles = {
    info: "border-l-brand bg-brand/5",
    tip: "border-l-green-500 bg-green-500/5",
    warning: "border-l-yellow-500 bg-yellow-500/5",
  };
  return (
    <div className={`border-l-4 rounded-r-lg px-4 py-3 my-4 ${styles[type]}`}>
      <div className="text-sm text-dim">{children}</div>
    </div>
  );
}

export function CodeTabs({ tabs }: { tabs: { label: string; code: string }[] }) {
  const [active, setActive] = useState(0);
  return (
    <div className="my-4 rounded-lg border border-border overflow-hidden">
      <div className="flex bg-surface border-b border-border">
        {tabs.map((tab, i) => (
          <button
            key={tab.label}
            onClick={() => setActive(i)}
            className={`px-4 py-2 text-xs font-medium transition-colors ${
              i === active ? "text-foreground bg-base border-b-2 border-brand" : "text-muted hover:text-foreground"
            }`}
          >
            {tab.label}
          </button>
        ))}
      </div>
      <pre className="bg-base p-4 overflow-x-auto text-sm text-dim font-mono">
        <code>{tabs[active].code}</code>
      </pre>
    </div>
  );
}

export function Code({ children }: { children: React.ReactNode }) {
  return <code className="bg-surface text-brand px-1.5 py-0.5 rounded text-[13px] font-mono">{children}</code>;
}

export function CodeBlock({ children }: { children: string }) {
  return (
    <pre className="bg-base border border-border rounded-lg p-4 overflow-x-auto text-sm text-dim my-4 font-mono">
      <code>{children}</code>
    </pre>
  );
}

export function H2({ children }: { children: React.ReactNode }) {
  return <h2 className="text-xl font-semibold text-foreground mt-8 mb-4 pb-2 border-b border-border font-display">{children}</h2>;
}

export function H3({ children }: { children: React.ReactNode }) {
  return <h3 className="text-base font-medium text-foreground mt-6 mb-2">{children}</h3>;
}

export function P({ children }: { children: React.ReactNode }) {
  return <p className="text-sm text-dim leading-relaxed mb-3">{children}</p>;
}

export function ParamTable({ params }: { params: { name: string; type: string; desc: string; required?: boolean }[] }) {
  return (
    <div className="my-4 border border-border rounded-lg overflow-hidden">
      <table className="w-full text-sm">
        <thead>
          <tr className="bg-surface">
            <th className="text-left px-4 py-2 text-xs font-medium text-muted uppercase">Parameter</th>
            <th className="text-left px-4 py-2 text-xs font-medium text-muted uppercase">Type</th>
            <th className="text-left px-4 py-2 text-xs font-medium text-muted uppercase">Description</th>
          </tr>
        </thead>
        <tbody>
          {params.map((p) => (
            <tr key={p.name} className="border-t border-border">
              <td className="px-4 py-2 font-mono text-foreground text-xs">
                {p.name}{p.required && <span className="text-red-400 ml-1">*</span>}
              </td>
              <td className="px-4 py-2 text-muted text-xs">{p.type}</td>
              <td className="px-4 py-2 text-dim text-xs">{p.desc}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export function Title({ children }: { children: React.ReactNode }) {
  return <h1 className="text-2xl font-bold text-foreground font-display mb-2">{children}</h1>;
}

export function Subtitle({ children }: { children: React.ReactNode }) {
  return <p className="text-sm text-dim mb-6">{children}</p>;
}
