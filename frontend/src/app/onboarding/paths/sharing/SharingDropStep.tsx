"use client";

import { useState } from "react";

import StashQuickAdd from "@/components/StashQuickAdd";
import type { StepCtx } from "@/lib/onboarding/paths";
import { buildPrompt, type ShareKind } from "@/app/onboarding/prompts";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:3456";

type OptionId = "drop" | "html" | "markdown" | "session";

const OPTIONS: { id: OptionId; title: string; blurb: string }[] = [
  {
    id: "drop",
    title: "Drag & drop a file",
    blurb: "A .jsonl session transcript, an HTML page, or a markdown doc.",
  },
  {
    id: "html",
    title: "Agent → HTML page",
    blurb: "Your coding agent generates an information-dense HTML page.",
  },
  {
    id: "markdown",
    title: "Agent → Markdown doc",
    blurb: "Research note, spec, or writeup — published as markdown.",
  },
  {
    id: "session",
    title: "Agent → Session trace",
    blurb: "Your agent uploads its own .jsonl transcript to share.",
  },
];

export default function SharingDropStep({ apiKey, workspaceId }: StepCtx) {
  const [selected, setSelected] = useState<OptionId>("drop");

  return (
    <div className="space-y-6">
      <div className="space-y-2">
        <h1 className="font-display text-[28px] leading-[1.1] font-bold tracking-tight text-foreground">
          How do you want to share?
        </h1>
        <p className="text-sm text-dim max-w-md">
          Either gets you a shareable link. Pick whichever&rsquo;s closer to
          where your content lives right now.
        </p>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-[220px_1fr] gap-4">
        <div className="flex flex-col gap-1.5">
          {OPTIONS.map((opt) => {
            const isActive = opt.id === selected;
            return (
              <button
                key={opt.id}
                type="button"
                onClick={() => setSelected(opt.id)}
                className={`text-left rounded-xl border p-3 transition-colors ${
                  isActive
                    ? "border-brand bg-brand/5"
                    : "border-border bg-surface hover:bg-raised hover:border-border"
                }`}
              >
                <div className="text-[12.5px] font-semibold text-foreground">
                  {opt.title}
                </div>
                <div className="mt-0.5 text-[11px] text-muted leading-snug">
                  {opt.blurb}
                </div>
              </button>
            );
          })}
        </div>

        <div className="rounded-2xl border border-border bg-surface p-4 min-h-[260px]">
          {selected === "drop" ? (
            workspaceId ? (
              <DropPanel workspaceId={workspaceId} />
            ) : (
              <div className="text-[12px] text-muted">Setting up workspace…</div>
            )
          ) : (
            <PromptPanel kind={selected} apiKey={apiKey} />
          )}
        </div>
      </div>
    </div>
  );
}

function DropPanel({ workspaceId }: { workspaceId: string }) {
  return (
    <div className="space-y-3">
      <div className="text-[11px] font-mono uppercase tracking-wider text-muted">
        Drag &amp; drop
      </div>
      <StashQuickAdd workspaceId={workspaceId} />
      <p className="text-[11px] text-muted leading-relaxed">
        <code className="text-foreground">.jsonl</code> becomes a session,{" "}
        <code className="text-foreground">.html</code> becomes a published
        page, <code className="text-foreground">.md</code> becomes a
        markdown page.
      </p>
    </div>
  );
}

function PromptPanel({ kind, apiKey }: { kind: ShareKind; apiKey: string }) {
  const [copied, setCopied] = useState(false);
  const prompt = buildPrompt(kind, apiKey, API_URL);

  async function handleCopy() {
    await navigator.clipboard.writeText(prompt);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  }

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
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
      <pre className="rounded-md border border-border-subtle bg-background/40 p-3 text-[11.5px] leading-relaxed text-foreground font-mono whitespace-pre-wrap break-all overflow-x-auto max-h-[360px]">
        {prompt}
      </pre>
      <p className="text-[11px] text-muted leading-relaxed">
        Paste into Claude Code, Cursor, or Codex. Your agent runs the command
        and prints back a <code className="text-foreground">/stashes/&hellip;</code>{" "}
        URL.
      </p>
    </div>
  );
}
