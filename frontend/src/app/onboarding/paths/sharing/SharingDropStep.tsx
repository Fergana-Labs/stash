"use client";

import { type DragEvent, type ReactNode, useRef, useState } from "react";

import { createPage, uploadFileOrPage, uploadTranscript } from "@/lib/api";
import type { StepCtx } from "@/lib/onboarding/paths";
import { buildPrompt, type ShareKind } from "@/app/onboarding/prompts";
import { usePublicApiBase } from "@/hooks/usePublicApiBase";

function Ext({ children }: { children: string }) {
  return <code className="text-foreground">{children}</code>;
}

type OptionId = "drop" | "html" | "markdown" | "session";

const OPTIONS: { id: OptionId; title: string; blurb: ReactNode }[] = [
  {
    id: "drop",
    title: "Drag & drop a file",
    blurb: (
      <>
        A <Ext>.jsonl</Ext> session, <Ext>.html</Ext> page, or <Ext>.md</Ext>{" "}
        doc from your machine.
      </>
    ),
  },
  {
    id: "html",
    title: "Agent → HTML page",
    blurb: (
      <>
        Have your agent publish a new or existing <Ext>.html</Ext> page.
      </>
    ),
  },
  {
    id: "markdown",
    title: "Agent → Markdown doc",
    blurb: (
      <>
        Have your agent publish a new or existing <Ext>.md</Ext> doc.
      </>
    ),
  },
  {
    id: "session",
    title: "Agent → Session trace",
    blurb: (
      <>
        Have your agent upload its current <Ext>.jsonl</Ext> transcript.
      </>
    ),
  },
];

export default function SharingDropStep({ apiKey, workspaceId }: StepCtx) {
  const [selected, setSelected] = useState<OptionId>("drop");

  return (
    <div className="space-y-6">
      <div>
        <h1 className="font-display text-[28px] leading-[1.1] font-bold tracking-tight text-foreground">
          What do you want to share?
        </h1>
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

type DropStatus =
  | { kind: "idle" }
  | { kind: "busy"; message: string }
  | { kind: "done"; message: string }
  | { kind: "error"; message: string };

const ACCEPT_EXTS = [".jsonl", ".html", ".md"] as const;
const ACCEPT_ATTR = ACCEPT_EXTS.join(",");

function DropPanel({ workspaceId }: { workspaceId: string }) {
  const [dragActive, setDragActive] = useState(false);
  const [status, setStatus] = useState<DropStatus>({ kind: "idle" });
  const fileInputRef = useRef<HTMLInputElement>(null);
  const dragDepth = useRef(0);

  async function handleFiles(list: FileList | File[]) {
    const files = Array.from(list);
    if (!files.length) return;

    const accepted: File[] = [];
    const rejected: string[] = [];
    for (const f of files) {
      if (matchesAllowed(f.name)) accepted.push(f);
      else rejected.push(f.name);
    }

    if (!accepted.length) {
      setStatus({
        kind: "error",
        message: `Only .jsonl, .html, and .md are accepted. Skipped: ${rejected.join(", ")}`,
      });
      return;
    }

    setStatus({
      kind: "busy",
      message:
        accepted.length === 1
          ? `Uploading ${accepted[0].name}…`
          : `Uploading ${accepted.length} files…`,
    });

    try {
      for (const f of accepted) {
        const lower = f.name.toLowerCase();
        if (lower.endsWith(".jsonl")) {
          const sessionId = f.name.replace(/\.jsonl$/i, "").trim() || "session";
          await uploadTranscript(workspaceId, f, sessionId, "manual-upload");
        } else if (lower.endsWith(".html") || lower.endsWith(".htm")) {
          await uploadFileOrPage(workspaceId, f);
        } else if (lower.endsWith(".md")) {
          const text = await f.text();
          const name = f.name.replace(/\.md$/i, "") || f.name;
          await createPage(workspaceId, name, null, text, {
            content_type: "markdown",
          });
        }
      }
    } catch (e) {
      setStatus({
        kind: "error",
        message: e instanceof Error ? e.message : "Upload failed",
      });
      return;
    }

    const parts: string[] = [];
    if (accepted.length) parts.push(`${accepted.length} added`);
    if (rejected.length) parts.push(`${rejected.length} skipped (unsupported)`);
    setStatus({ kind: "done", message: parts.join(" · ") });
  }

  function isFilesDrag(e: DragEvent) {
    return Array.from(e.dataTransfer.types).includes("Files");
  }

  function onDragEnter(e: DragEvent) {
    if (!isFilesDrag(e)) return;
    e.preventDefault();
    e.stopPropagation();
    dragDepth.current += 1;
    setDragActive(true);
  }

  function onDragLeave(e: DragEvent) {
    if (!isFilesDrag(e)) return;
    e.preventDefault();
    e.stopPropagation();
    dragDepth.current = Math.max(0, dragDepth.current - 1);
    if (dragDepth.current === 0) setDragActive(false);
  }

  function onDragOver(e: DragEvent) {
    if (!isFilesDrag(e)) return;
    e.preventDefault();
    e.stopPropagation();
    e.dataTransfer.dropEffect = "copy";
  }

  function onDrop(e: DragEvent) {
    if (!isFilesDrag(e)) return;
    e.preventDefault();
    e.stopPropagation();
    dragDepth.current = 0;
    setDragActive(false);
    void handleFiles(e.dataTransfer.files);
  }

  return (
    <div className="space-y-3">
      <div className="text-[11px] font-mono uppercase tracking-wider text-muted">
        Drag &amp; drop
      </div>

      <button
        type="button"
        onClick={() => fileInputRef.current?.click()}
        onDragEnter={onDragEnter}
        onDragLeave={onDragLeave}
        onDragOver={onDragOver}
        onDrop={onDrop}
        className={`w-full flex flex-col items-center justify-center gap-2 rounded-xl border-2 border-dashed px-6 py-10 text-center transition-colors ${
          dragActive
            ? "border-brand bg-brand/10"
            : "border-border bg-background/40 hover:border-brand hover:bg-raised"
        }`}
      >
        <div className="text-[24px] leading-none" aria-hidden>
          ⬆
        </div>
        <div className="text-[13px] font-medium text-foreground">
          {dragActive ? "Release to upload" : "Drop a file, or click to pick one"}
        </div>
        <div className="text-[11px] text-muted">
          <code className="text-foreground">.jsonl</code> ·{" "}
          <code className="text-foreground">.html</code> ·{" "}
          <code className="text-foreground">.md</code>
        </div>
      </button>

      <input
        ref={fileInputRef}
        type="file"
        accept={ACCEPT_ATTR}
        multiple
        className="hidden"
        onChange={(e) => {
          if (e.target.files?.length) void handleFiles(e.target.files);
          if (fileInputRef.current) fileInputRef.current.value = "";
        }}
      />

      {status.kind !== "idle" && (
        <p
          className={`text-[11.5px] ${
            status.kind === "error"
              ? "text-error"
              : status.kind === "done"
                ? "text-brand"
                : "text-muted"
          }`}
        >
          {status.message}
        </p>
      )}

      <p className="text-[11px] text-muted leading-relaxed">
        Upload a <Ext>.jsonl</Ext> of a session, an <Ext>.html</Ext> page,
        or a <Ext>.md</Ext> doc.
      </p>
    </div>
  );
}

function matchesAllowed(name: string): boolean {
  const lower = name.toLowerCase();
  return (
    lower.endsWith(".jsonl") ||
    lower.endsWith(".html") ||
    lower.endsWith(".htm") ||
    lower.endsWith(".md")
  );
}

function PromptPanel({ kind, apiKey }: { kind: ShareKind; apiKey: string }) {
  const [copied, setCopied] = useState(false);
  const apiUrl = usePublicApiBase();
  const prompt = apiUrl ? buildPrompt(kind, apiKey, apiUrl) : "Preparing Stash URL...";

  async function handleCopy() {
    if (!apiUrl) return;
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
          disabled={!apiUrl}
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
