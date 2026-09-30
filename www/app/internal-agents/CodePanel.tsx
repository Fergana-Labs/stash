"use client";

import { useState } from "react";

type Pane = "cli" | "mcp";

const TABS: [Pane, string, string][] = [
  ["cli", "CLI", "terminal"],
  ["mcp", "MCP", "json"],
];

const C = "text-[rgba(250,248,245,0.36)]";
const W = "text-[#FBF8F3]";
const OK = "text-[#6FCF97]";
const P = "text-brand";

export default function CodePanel() {
  const [pane, setPane] = useState<Pane>("cli");
  const lang = TABS.find(([id]) => id === pane)![2];

  return (
    <div className="mx-auto mt-9 max-w-[880px] md:mt-14">
      <div
        role="tablist"
        aria-label="How to connect Stash"
        className="mx-auto flex w-fit gap-1 rounded-[11px] border border-border-subtle bg-surface p-[5px]"
      >
        {TABS.map(([id, label]) => (
          <button
            key={id}
            role="tab"
            type="button"
            aria-selected={pane === id}
            onClick={() => setPane(id)}
            className={`rounded-[7px] px-4 py-2 text-[14px] transition ${
              pane === id ? "bg-white text-ink shadow-sm" : "text-dim hover:text-ink"
            }`}
          >
            {label}
          </button>
        ))}
      </div>

      <div className="mt-[18px] overflow-hidden rounded-[14px] bg-inverted shadow-[var(--shadow-terminal)]">
        <div className="flex items-center justify-between border-b border-white/[0.07] px-3.5 py-[11px]">
          <span className="flex gap-1.5">
            <i className="block h-2.5 w-2.5 rounded-full bg-white/15" />
            <i className="block h-2.5 w-2.5 rounded-full bg-white/15" />
            <i className="block h-2.5 w-2.5 rounded-full bg-white/15" />
          </span>
          <span className="font-mono text-[11.5px] uppercase tracking-[0.08em] text-[rgba(250,248,245,0.42)]">
            {lang}
          </span>
        </div>
        <pre className="overflow-x-auto px-[22px] py-5 text-left font-mono text-[13px] leading-[1.95] text-[rgba(250,248,245,0.7)]">
          {pane === "cli" && (
            <>
              <span className={P}>$</span> <span className={W}>stash plugin install</span>
              {"\n"}
              <span className={C}>claude-code, cursor, codex, opencode</span>
              {"\n\n"}
              <span className={P}>$</span> <span className={W}>stash import</span> ~/.claude/projects
              {"\n"}
              <span className={OK}>✓</span> 412 sessions <span className={C}>· 18.4M tokens</span>
              {"\n\n"}
              <span className={P}>$</span> <span className={W}>stash refine</span>
              {"\n"}
              <span className={OK}>✓</span> wrote 34 pages, 6 skills
            </>
          )}
          {pane === "mcp" && (
            <>
              <span className={C}>{"// .mcp.json"}</span>
              {"\n"}
              <span className={W}>{"{"}</span>
              {"\n  "}
              <span className={W}>&quot;mcpServers&quot;</span>: {"{"}
              {"\n    "}
              <span className={W}>&quot;stash&quot;</span>: {"{"}
              {"\n      "}
              <span className={W}>&quot;command&quot;</span>:{" "}
              <span className={OK}>&quot;stash-mcp&quot;</span>
              {"\n    }\n  }\n"}
              <span className={W}>{"}"}</span>
              {"\n\n"}
              <span className={C}>{"// the agent now reads your Stash as a filesystem"}</span>
            </>
          )}
        </pre>
      </div>
    </div>
  );
}
