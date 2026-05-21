"use client";

import { type DragEvent, useEffect, useRef, useState } from "react";

import { apiFetch, uploadTranscript } from "@/lib/api";
import type { StepCtx } from "@/lib/onboarding/paths";

type Overview = {
  sessions: unknown[];
};

// Skip ahead if the workspace already has session transcripts — memory
// works on whatever's already there, no need to make the user upload again.
export default function MemoryImportStep(ctx: StepCtx) {
  const [checked, setChecked] = useState(false);

  useEffect(() => {
    if (!ctx.workspaceId) return;
    let cancelled = false;
    apiFetch<Overview>(`/api/v1/workspaces/${ctx.workspaceId}/overview`)
      .then((o) => {
        if (cancelled) return;
        if ((o.sessions?.length ?? 0) > 0) {
          ctx.onContinue();
        } else {
          setChecked(true);
        }
      })
      .catch(() => {
        if (!cancelled) setChecked(true);
      });
    return () => {
      cancelled = true;
    };
  }, [ctx]);

  if (!checked) {
    return <div className="text-sm text-muted">Checking your workspace…</div>;
  }

  return (
    <div className="space-y-6">
      <div className="space-y-2">
        <h1 className="font-display text-[28px] leading-[1.1] font-bold tracking-tight text-foreground">
          Give your agent something to remember
        </h1>
        <p className="text-sm text-dim max-w-md">
          Install the CLI to auto-push every coding session, or drop a
          transcript in directly.
        </p>
      </div>

      <CliCard />
      {ctx.workspaceId && <TranscriptDrop workspaceId={ctx.workspaceId} />}
    </div>
  );
}

function CliCard() {
  return (
    <div className="rounded-2xl border border-border bg-surface p-5 space-y-2">
      <div className="text-[13px] font-semibold text-foreground">
        Install the CLI
      </div>
      <p className="text-[12.5px] text-muted leading-relaxed">
        First-run signs you in automatically. From then on, every coding
        session — Claude Code, Codex, Openclaw — auto-pushes its{" "}
        <code className="text-foreground">.jsonl</code> transcript into your
        workspace.
      </p>
      <pre className="rounded-md border border-border-subtle bg-background/40 px-3 py-2 text-[12px] font-mono text-foreground overflow-x-auto">
        npm i -g @joinstash/cli
      </pre>
    </div>
  );
}

type DropStatus =
  | { kind: "idle" }
  | { kind: "busy"; message: string }
  | { kind: "done"; message: string }
  | { kind: "error"; message: string };

function TranscriptDrop({ workspaceId }: { workspaceId: string }) {
  const [dragActive, setDragActive] = useState(false);
  const [status, setStatus] = useState<DropStatus>({ kind: "idle" });
  const fileInputRef = useRef<HTMLInputElement>(null);
  const dragDepth = useRef(0);

  async function handleFiles(list: FileList | File[]) {
    const files = Array.from(list);
    if (!files.length) return;
    const accepted = files.filter((f) => f.name.toLowerCase().endsWith(".jsonl"));
    const rejected = files.filter((f) => !f.name.toLowerCase().endsWith(".jsonl"));
    if (!accepted.length) {
      setStatus({
        kind: "error",
        message: `Only .jsonl transcripts are accepted. Skipped: ${rejected.map((f) => f.name).join(", ")}`,
      });
      return;
    }
    setStatus({
      kind: "busy",
      message:
        accepted.length === 1
          ? `Uploading ${accepted[0].name}…`
          : `Uploading ${accepted.length} transcripts…`,
    });
    try {
      for (const f of accepted) {
        const sessionId = f.name.replace(/\.jsonl$/i, "").trim() || "session";
        await uploadTranscript(workspaceId, f, sessionId, "manual-upload");
      }
    } catch (e) {
      setStatus({
        kind: "error",
        message: e instanceof Error ? e.message : "Upload failed",
      });
      return;
    }
    setStatus({
      kind: "done",
      message: `${accepted.length} transcript${accepted.length === 1 ? "" : "s"} uploaded`,
    });
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
    <div className="rounded-2xl border border-border bg-surface p-5 space-y-3">
      <div className="text-[13px] font-semibold text-foreground">
        Or drop a transcript
      </div>
      <p className="text-[12.5px] text-muted leading-relaxed">
        Have a <code className="text-foreground">.jsonl</code> session
        already? Drop it here. Claude Code stores them at{" "}
        <code className="text-foreground">~/.claude/projects/&lt;dir&gt;/&lt;id&gt;.jsonl</code>.
      </p>

      <button
        type="button"
        onClick={() => fileInputRef.current?.click()}
        onDragEnter={onDragEnter}
        onDragLeave={onDragLeave}
        onDragOver={onDragOver}
        onDrop={onDrop}
        className={`w-full flex flex-col items-center justify-center gap-1.5 rounded-xl border-2 border-dashed px-6 py-8 text-center transition-colors ${
          dragActive
            ? "border-brand bg-brand/10"
            : "border-border bg-background/40 hover:border-brand hover:bg-raised"
        }`}
      >
        <div className="text-[20px] leading-none" aria-hidden>
          ⬆
        </div>
        <div className="text-[12.5px] font-medium text-foreground">
          {dragActive ? "Release to upload" : "Drop a .jsonl file, or click to pick one"}
        </div>
      </button>

      <input
        ref={fileInputRef}
        type="file"
        accept=".jsonl"
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
    </div>
  );
}
