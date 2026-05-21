"use client";

import { useEffect, useState } from "react";

import { apiFetch } from "@/lib/api";
import type { StepCtx } from "@/lib/onboarding/paths";

type Overview = {
  sessions: { session_id?: string; name?: string }[];
  files: {
    pages: { id: string; name: string }[];
  };
};

// Step 2: the elevator pitch. A side-by-side panel showing the cost of
// re-explaining context to a stateless agent vs. asking a one-liner of an
// agent that has memory. The "topic" is pulled from the user's actual
// workspace when possible (a recent page name, or a recent session ID)
// so the example feels personal; falls back to a canned example otherwise.
export default function MemoryDemoStep({ workspaceId }: StepCtx) {
  const [topic, setTopic] = useState<string | null>(null);
  const [grounding, setGrounding] = useState<
    | { kind: "none" }
    | { kind: "sessions"; count: number }
    | { kind: "pages"; count: number }
  >({ kind: "none" });

  useEffect(() => {
    if (!workspaceId) return;
    apiFetch<Overview>(`/api/v1/workspaces/${workspaceId}/overview`)
      .then((o) => {
        const sessions = o.sessions ?? [];
        const pages = o.files?.pages ?? [];
        if (pages.length > 0) {
          setTopic(pages[0].name);
        } else if (sessions.length > 0) {
          const s = sessions[0];
          setTopic(s.name || s.session_id || "your last session");
        }
        if (sessions.length > 0) {
          setGrounding({ kind: "sessions", count: sessions.length });
        } else if (pages.length > 0) {
          setGrounding({ kind: "pages", count: pages.length });
        } else {
          setGrounding({ kind: "none" });
        }
      })
      .catch(() => {});
  }, [workspaceId]);

  const displayTopic = topic ?? "the API gateway refactor";

  return (
    <div className="space-y-6">
      <div className="space-y-2">
        <h1 className="font-display text-[28px] leading-[1.1] font-bold tracking-tight text-foreground">
          Stop re-explaining yourself to your agent
        </h1>
        <p className="text-sm text-dim max-w-md">
          Every conversation, the agent forgets. You re-paste context, restate
          constraints, replay the last decision. With memory of your past
          sessions, you just pick up the thread.
        </p>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
        <div className="rounded-xl border border-border-subtle bg-background/40 p-4 opacity-70 min-h-[200px] flex flex-col">
          <div className="text-[10px] font-mono uppercase tracking-wider text-muted mb-2">
            Without memory
          </div>
          <pre className="font-mono text-[10.5px] text-muted leading-snug whitespace-pre-wrap flex-1">
{`# Context

Last week I was working on
${displayTopic}. Here's where
I left off:

[paste 3,200 chars of the
 session transcript]
[restate the open questions]
[list the constraints again]
[mention the dead ends]

OK, continue from there.`}
          </pre>
        </div>

        <div className="rounded-xl border border-brand bg-brand/5 p-4 min-h-[200px] flex flex-col">
          <div className="text-[10px] font-mono uppercase tracking-wider text-brand mb-2">
            With Stash
          </div>
          <div className="flex-1 flex flex-col gap-3">
            <div className="font-mono text-[12.5px] text-foreground">
              Pick up where we left off on{" "}
              <span className="text-brand">{displayTopic}</span>.
            </div>
            <GroundingBadge grounding={grounding} />
            <div className="mt-auto text-[11px] text-muted italic leading-relaxed">
              Same conversation, no scaffolding. Your agent already knows the
              context.
            </div>
          </div>
        </div>
      </div>

      <p className="text-[11.5px] text-dim leading-relaxed">
        Stash saves you the prompt-writing tax: the long context dumps, the
        repeated explanations, the back-and-forth to get your agent caught up.
      </p>
    </div>
  );
}

function GroundingBadge({
  grounding,
}: {
  grounding:
    | { kind: "none" }
    | { kind: "sessions"; count: number }
    | { kind: "pages"; count: number };
}) {
  if (grounding.kind === "none") {
    return (
      <div className="inline-flex items-center gap-1.5 self-start rounded-full bg-background/60 border border-border-subtle px-2 py-0.5 text-[10.5px] text-muted">
        <span className="w-1 h-1 rounded-full bg-muted" />
        what your agent would know
      </div>
    );
  }
  const label =
    grounding.kind === "sessions"
      ? `grounded on your ${grounding.count} session${grounding.count === 1 ? "" : "s"}`
      : `grounded on your ${grounding.count} page${grounding.count === 1 ? "" : "s"}`;
  return (
    <div className="inline-flex items-center gap-1.5 self-start rounded-full bg-background/60 border border-border-subtle px-2 py-0.5 text-[10.5px] text-muted">
      <span className="w-1 h-1 rounded-full bg-brand" />
      {label}
    </div>
  );
}
