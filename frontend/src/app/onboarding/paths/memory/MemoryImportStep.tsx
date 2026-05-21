"use client";

import { useEffect, useRef, useState } from "react";

import { apiFetch } from "@/lib/api";
import type { StepCtx } from "@/lib/onboarding/paths";

type Overview = {
  sessions: unknown[];
};

const POLL_INTERVAL_MS = 4000;
const AUTO_ADVANCE_DELAY_MS = 1500;

// Step 1: install the CLI and wait for the first session to land. The CLI
// auto-pushes session transcripts to /workspaces/{id}/transcripts on first
// run, so we poll the workspace overview until sessions appear, then auto-
// advance. User can bypass with the "Skip — show me how it works" link.
export default function MemoryImportStep(ctx: StepCtx) {
  const [sessionCount, setSessionCount] = useState<number | null>(null);
  const [skipping, setSkipping] = useState(false);
  const advanceTimer = useRef<number | null>(null);

  // Polling: hit /overview every 4s while we have a workspace and no
  // sessions detected yet. Stops as soon as sessions > 0 or step unmounts.
  useEffect(() => {
    if (!ctx.workspaceId) return;
    let cancelled = false;

    async function tick() {
      try {
        const o = await apiFetch<Overview>(
          `/api/v1/workspaces/${ctx.workspaceId}/overview`,
        );
        if (cancelled) return;
        const n = o.sessions?.length ?? 0;
        setSessionCount(n);
      } catch {
        // Transient errors: try again next tick.
      }
    }

    void tick();
    const id = window.setInterval(tick, POLL_INTERVAL_MS);
    return () => {
      cancelled = true;
      window.clearInterval(id);
    };
  }, [ctx.workspaceId]);

  // Auto-advance once sessions are detected — unless the user explicitly
  // skipped, in which case onContinue already fired.
  useEffect(() => {
    if (skipping) return;
    if (sessionCount !== null && sessionCount > 0) {
      advanceTimer.current = window.setTimeout(() => {
        ctx.onContinue();
      }, AUTO_ADVANCE_DELAY_MS);
    }
    return () => {
      if (advanceTimer.current !== null) {
        window.clearTimeout(advanceTimer.current);
        advanceTimer.current = null;
      }
    };
  }, [sessionCount, skipping, ctx]);

  function handleSkip() {
    setSkipping(true);
    ctx.onContinue();
  }

  const detected = sessionCount !== null && sessionCount > 0;

  return (
    <div className="space-y-6">
      <div className="space-y-2">
        <h1 className="font-display text-[28px] leading-[1.1] font-bold tracking-tight text-foreground">
          Give your agent something to remember
        </h1>
        <p className="text-sm text-dim max-w-md">
          Install the CLI. First run signs you in automatically. From then on,
          every coding session (Claude Code, Codex, Openclaw) auto-pushes its
          transcript here.
        </p>
      </div>

      <div className="rounded-2xl border border-border bg-surface p-5 space-y-3">
        <div className="text-[13px] font-semibold text-foreground">
          Install the CLI
        </div>
        <pre className="rounded-md border border-border-subtle bg-background/40 px-3 py-2 text-[12px] font-mono text-foreground overflow-x-auto">
          npm i -g @joinstash/cli
        </pre>
      </div>

      <StatusPanel detected={detected} sessionCount={sessionCount ?? 0} />

      <div>
        <button
          type="button"
          onClick={handleSkip}
          className="text-[12px] text-muted hover:text-foreground transition-colors underline"
        >
          Skip — show me how it works anyway
        </button>
      </div>
    </div>
  );
}

function StatusPanel({
  detected,
  sessionCount,
}: {
  detected: boolean;
  sessionCount: number;
}) {
  if (detected) {
    return (
      <div className="rounded-xl border border-brand bg-brand/5 px-4 py-3 flex items-center gap-3">
        <span
          className="flex h-6 w-6 items-center justify-center rounded-full bg-brand text-white text-[12px] font-bold"
          aria-hidden
        >
          ✓
        </span>
        <div className="text-[12.5px] text-foreground">
          Detected {sessionCount} session{sessionCount === 1 ? "" : "s"} from
          your CLI — your agent has memory now.
        </div>
      </div>
    );
  }

  return (
    <div className="rounded-xl border border-border-subtle bg-background/40 px-4 py-3 flex items-center gap-3">
      <span className="relative flex h-2.5 w-2.5" aria-hidden>
        <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-brand opacity-60" />
        <span className="relative inline-flex h-2.5 w-2.5 rounded-full bg-brand" />
      </span>
      <div className="text-[12.5px] text-muted">
        Waiting for your first session…
      </div>
    </div>
  );
}
