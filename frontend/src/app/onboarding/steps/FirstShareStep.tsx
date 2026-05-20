"use client";

import { useState } from "react";

import { buildPrompt, ShareKind } from "../prompts";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:3456";

const TABS: { kind: ShareKind; label: string; hint: string }[] = [
  { kind: "html", label: "HTML page", hint: "Information-dense, optimized to read once." },
  { kind: "markdown", label: "Markdown doc", hint: "Research note, spec, or writeup." },
  { kind: "session", label: "Session trace", hint: "Share the agent's own transcript." },
];

type Props = {
  apiKey: string;
};

export default function FirstShareStep({ apiKey }: Props) {
  const [kind, setKind] = useState<ShareKind>("html");
  const [copied, setCopied] = useState(false);
  const prompt = buildPrompt(kind, apiKey, API_URL);

  async function handleCopy() {
    await navigator.clipboard.writeText(prompt);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  }

  return (
    <div className="space-y-6">
      <div className="space-y-2">
        <h1 className="font-display text-[28px] leading-[1.1] font-bold tracking-tight text-foreground">
          Make your first share
        </h1>
        <p className="text-sm text-dim max-w-md">
          Paste this into Claude Code, Cursor, or Codex. Your agent will
          generate the content and publish it — you&rsquo;ll get a share URL
          back.
        </p>
      </div>

      <div className="rounded-2xl border border-border bg-surface overflow-hidden">
        <div className="flex border-b border-border bg-background/40">
          {TABS.map((t) => (
            <button
              key={t.kind}
              type="button"
              onClick={() => setKind(t.kind)}
              className={`flex-1 px-3 py-2.5 text-[12px] font-medium border-b-2 transition-colors ${
                kind === t.kind
                  ? "border-brand text-foreground"
                  : "border-transparent text-muted hover:text-foreground"
              }`}
            >
              {t.label}
            </button>
          ))}
        </div>

        <div className="px-4 pt-3 pb-2 text-[11px] text-muted">
          {TABS.find((t) => t.kind === kind)?.hint}
        </div>

        <div className="flex items-center justify-between px-4 py-2 border-t border-border-subtle bg-background/40">
          <div className="text-[11px] font-mono uppercase tracking-wider text-muted">
            Prompt + curl
          </div>
          <button
            type="button"
            onClick={handleCopy}
            className="text-[11px] font-medium text-brand hover:text-brand-hover transition-colors"
          >
            {copied ? "Copied" : "Copy"}
          </button>
        </div>

        <pre className="p-4 text-[12px] leading-relaxed text-foreground font-mono whitespace-pre-wrap break-all overflow-x-auto max-h-[420px]">
          {prompt}
        </pre>
      </div>

      <div className="rounded-xl border border-border-subtle bg-background/40 p-4 text-[12px] text-dim leading-relaxed">
        <strong className="text-foreground font-medium">What happens next:</strong>{" "}
        your agent runs the command and prints a URL like{" "}
        <code className="text-foreground">{`${API_URL.replace(/\/$/, "")}/stashes/...`}</code>
        . Open it — your content is live and shareable.
      </div>
    </div>
  );
}
