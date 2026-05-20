"use client";

import { useEffect, useState } from "react";

import MigrantImportStep from "../migrant/MigrantImportStep";
import type { MigrantSource, StepCtx } from "@/lib/onboarding/paths";
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
          Bring in past sessions, notes, or docs — anything your agent
          should know about your work. Drop transcripts via the CLI, or
          pull from a source below.
        </p>
      </div>

      {ctx.source ? (
        <MigrantImportStep {...ctx} />
      ) : (
        <SourcePickerInline onPick={ctx.setSource} />
      )}
    </div>
  );
}

// Mini-picker used inside the memory path's import gate. Doesn't advance
// the step — just sets ?source= so the same step re-renders with the
// matching import surface (MigrantImportStep dispatches on source).
function SourcePickerInline({ onPick }: { onPick: (s: MigrantSource) => void }) {
  const CARDS: { id: MigrantSource; title: string; pitch: string }[] = [
    { id: "notion", title: "Notion", pitch: "Pages, databases, sub-pages." },
    { id: "obsidian", title: "Obsidian", pitch: "Drop your vault folder." },
    { id: "github", title: "GitHub", pitch: "A repo's worth of markdown." },
    { id: "drive", title: "Google Drive", pitch: "Folders, Docs, Sheets." },
  ];
  return (
    <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
      {CARDS.map((c) => (
        <button
          key={c.id}
          type="button"
          onClick={() => onPick(c.id)}
          className="text-left rounded-2xl border border-border bg-surface p-4 hover:bg-raised hover:border-brand transition-colors space-y-1.5"
        >
          <div className="text-[13px] font-semibold text-foreground">{c.title}</div>
          <div className="text-[12px] text-muted">{c.pitch}</div>
        </button>
      ))}
    </div>
  );
}
