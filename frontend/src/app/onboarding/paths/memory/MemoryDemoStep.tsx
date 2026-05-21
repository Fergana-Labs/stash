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

// Step 2: the elevator pitch. Stylized timeline diagram contrasting the
// long context-establishing dance you'd do without memory vs. the single
// line you'd say with it. Topic is pulled from the user's workspace when
// possible; falls back to a generic example.
export default function MemoryDemoStep({ workspaceId }: StepCtx) {
  const [topic, setTopic] = useState<string | null>(null);

  useEffect(() => {
    if (!workspaceId) return;
    apiFetch<Overview>(`/api/v1/workspaces/${workspaceId}/overview`)
      .then((o) => {
        const pages = o.files?.pages ?? [];
        const sessions = o.sessions ?? [];
        if (pages.length > 0) {
          setTopic(pages[0].name);
        } else if (sessions.length > 0) {
          const s = sessions[0];
          setTopic(s.name || s.session_id || "your last session");
        }
      })
      .catch(() => {});
  }, [workspaceId]);

  const displayTopic = topic ?? "the API gateway refactor";

  const beforeSteps = [
    `Paste 3,200 chars from last week's session about ${displayTopic}`,
    "Restate the open questions",
    "List the constraints again",
    "Recap what we tried and what didn't work",
    `“OK, now keep going on ${displayTopic}.”`,
  ];

  const afterSteps = [
    {
      text: `“Pick up where we left off on ${displayTopic}.”`,
      emphasis: true,
    },
  ];

  return (
    <div className="space-y-6">
      <h1 className="font-display text-[28px] leading-[1.1] font-bold tracking-tight text-foreground">
        Stop re-explaining yourself
      </h1>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <Column
          label="Without memory"
          tone="muted"
          steps={beforeSteps.map((s) => ({ text: s, emphasis: false }))}
        />
        <Column label="With Stash" tone="brand" steps={afterSteps} />
      </div>

      <p className="text-center text-[15px] font-display font-semibold tracking-tight text-foreground pt-2">
        Stop re-explaining. Start where you left off.
      </p>
    </div>
  );
}

type Step = { text: string; emphasis: boolean };

function Column({
  label,
  tone,
  steps,
}: {
  label: string;
  tone: "muted" | "brand";
  steps: Step[];
}) {
  const isBrand = tone === "brand";
  return (
    <div
      className={`rounded-xl border p-5 min-h-[280px] flex flex-col ${
        isBrand
          ? "border-brand bg-brand/5"
          : "border-border-subtle bg-background/40"
      }`}
    >
      <div
        className={`text-[10px] font-mono uppercase tracking-wider mb-4 ${
          isBrand ? "text-brand" : "text-muted"
        }`}
      >
        {label}
      </div>

      <ol className="relative flex flex-col gap-3">
        {steps.map((step, i) => (
          <li key={i} className="relative flex items-start gap-3">
            {/* connector line down to next bullet */}
            {i < steps.length - 1 && (
              <span
                className={`absolute left-[5px] top-[14px] bottom-[-12px] w-px ${
                  isBrand ? "bg-brand/40" : "bg-border"
                }`}
                aria-hidden
              />
            )}
            <span
              className={`mt-[3px] block h-2.5 w-2.5 shrink-0 rounded-full border-2 ${
                isBrand
                  ? "border-brand bg-brand"
                  : "border-border-subtle bg-background"
              }`}
              aria-hidden
            />
            <span
              className={`text-[12.5px] leading-relaxed ${
                step.emphasis
                  ? "text-foreground font-medium"
                  : isBrand
                    ? "text-foreground"
                    : "text-muted"
              }`}
            >
              {step.text}
            </span>
          </li>
        ))}
      </ol>
    </div>
  );
}
