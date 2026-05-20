"use client";

import { useEffect, useState } from "react";

import MigrantImportStep from "../migrant/MigrantImportStep";
import type { StepCtx } from "@/lib/onboarding/paths";
import { apiFetch } from "@/lib/api";

type Overview = {
  sessions: unknown[];
  files: { folders: unknown[]; pages: unknown[]; files: unknown[] };
  stashes: unknown[];
};

// If the workspace already has content, skip ahead automatically. Otherwise
// reuse MigrantImportStep — the import surfaces are the same, only the
// framing changes.
export default function MemoryImportStep(ctx: StepCtx) {
  const [checked, setChecked] = useState(false);

  useEffect(() => {
    if (!ctx.workspaceId) return;
    let cancelled = false;
    apiFetch<Overview>(`/api/v1/workspaces/${ctx.workspaceId}/overview`)
      .then((o) => {
        if (cancelled) return;
        const pageCount = o.files?.pages?.length ?? 0;
        const fileCount = o.files?.files?.length ?? 0;
        const sessionCount = o.sessions?.length ?? 0;
        const hasContent = pageCount + fileCount + sessionCount > 0;
        if (hasContent) {
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
          Memory works on what you&rsquo;ve imported. Bring in a source first —
          we&rsquo;ll show you the magical bit in the next step.
        </p>
      </div>

      <MigrantImportStep {...ctx} />
    </div>
  );
}
