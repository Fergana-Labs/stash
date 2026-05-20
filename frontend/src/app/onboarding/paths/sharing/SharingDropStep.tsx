"use client";

import FirstShareStep from "@/app/onboarding/steps/FirstShareStep";
import StashQuickAdd from "@/components/StashQuickAdd";
import type { StepCtx } from "@/lib/onboarding/paths";

export default function SharingDropStep({ apiKey, workspaceId }: StepCtx) {
  return (
    <div className="space-y-6">
      <div className="space-y-2">
        <h1 className="font-display text-[28px] leading-[1.1] font-bold tracking-tight text-foreground">
          Drop a file, or have your agent publish
        </h1>
        <p className="text-sm text-dim max-w-md">
          Either gets you a shareable link. Pick whichever&rsquo;s closer to
          where your content lives right now.
        </p>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <div className="rounded-2xl border border-border bg-surface p-4 space-y-3">
          <div className="text-[11px] font-mono uppercase tracking-wider text-muted">
            Drag &amp; drop
          </div>
          {workspaceId ? (
            <StashQuickAdd workspaceId={workspaceId} />
          ) : (
            <div className="text-[12px] text-muted">Setting up workspace…</div>
          )}
          <p className="text-[11px] text-muted leading-relaxed">
            Drop any file. HTML and markdown render inline; everything else
            lands in Files with text extraction queued automatically.
          </p>
        </div>

        <div className="rounded-2xl border border-border bg-surface p-4 space-y-3">
          <div className="text-[11px] font-mono uppercase tracking-wider text-muted">
            Have your agent publish
          </div>
          <FirstShareStepInline apiKey={apiKey} />
        </div>
      </div>
    </div>
  );
}

// Tighter wrapper around FirstShareStep — strips its outer heading/blurb
// so it sits cleanly inside the right-hand card.
function FirstShareStepInline({ apiKey }: { apiKey: string }) {
  return (
    <div className="[&>div>div:first-child]:hidden">
      <FirstShareStep apiKey={apiKey} />
    </div>
  );
}
