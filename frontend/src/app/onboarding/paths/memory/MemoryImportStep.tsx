"use client";

import { useEffect, useState } from "react";

import { apiFetch } from "@/lib/api";
import type { StepCtx } from "@/lib/onboarding/paths";

type Overview = {
  sessions: unknown[];
};

const POLL_INTERVAL_MS = 4000;

// Step 1: install the CLI and wait for sessions to land. The CLI auto-pushes
// session transcripts to /workspaces/{id}/transcripts (including a backfill
// of past sessions on first run), so we poll the workspace overview and
// surface the live count. User clicks Continue when they're ready — we
// don't auto-advance, since backfill can take a while and we can't reliably
// tell when it's "done."
export default function MemoryImportStep(ctx: StepCtx) {
  const [sessionCount, setSessionCount] = useState<number | null>(null);

  useEffect(() => {
    if (!ctx.workspaceId) return;
    let cancelled = false;

    async function tick() {
      try {
        const o = await apiFetch<Overview>(
          `/api/v1/workspaces/${ctx.workspaceId}/overview`,
        );
        if (cancelled) return;
        setSessionCount(o.sessions?.length ?? 0);
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
          pip install stashai
        </pre>
        <p className="text-[11.5px] text-muted leading-relaxed">
          On first run the CLI offers to <strong>backfill all your past
          sessions</strong> — so your agent has memory of work it&rsquo;s
          already done, not just what comes next.
        </p>
      </div>

      <StatusPanel detected={detected} sessionCount={sessionCount} />

      {detected && (
        <button
          type="button"
          onClick={ctx.onContinue}
          className="w-full rounded-md bg-brand px-4 py-2.5 text-[13px] font-medium text-white hover:bg-brand-hover"
        >
          Continue
        </button>
      )}

      <div>
        <button
          type="button"
          onClick={ctx.onContinue}
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
  sessionCount: number | null;
}) {
  if (detected && sessionCount !== null) {
    return (
      <div className="rounded-xl border border-brand bg-brand/5 px-4 py-3 space-y-1.5">
        <div className="flex items-center gap-2">
          <span
            className="flex h-5 w-5 items-center justify-center rounded-full bg-brand text-white text-[10px] font-bold"
            aria-hidden
          >
            ✓
          </span>
          <div className="text-[12.5px] text-foreground">
            Your CLI is connected.{" "}
            <strong>
              {sessionCount} session{sessionCount === 1 ? "" : "s"} uploaded
            </strong>{" "}
            so far.
          </div>
        </div>
        <p className="text-[11.5px] text-muted pl-7">
          If you started a backfill, wait until it finishes before continuing
          — your agent&rsquo;s memory is only as good as what&rsquo;s up
          here.
        </p>
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
        Waiting for the CLI to connect…
      </div>
    </div>
  );
}
