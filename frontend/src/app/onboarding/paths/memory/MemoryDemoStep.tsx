"use client";

import { useEffect, useState } from "react";

import { apiFetch } from "@/lib/api";
import type { StepCtx } from "@/lib/onboarding/paths";

type Demo = {
  topic: string;
  before_steps: string[];
  after_step: string;
  real: boolean;
};

const FALLBACK: Demo = {
  topic: "the API gateway refactor",
  before_steps: [
    "Paste 3,200 chars from last week's session",
    "Restate the open questions",
    "List the constraints again",
    "Recap what we tried and what didn't work",
    "“OK, now keep going on the API gateway refactor.”",
  ],
  after_step: "“Pick up where we left off on the API gateway refactor.”",
  real: false,
};

// Step 2: the elevator pitch. Calls /memory-demo which hits Claude when
// the workspace has real sessions, otherwise returns a canned demo. We
// show a small "Example from your last session" tag when the demo is
// grounded on real data.
export default function MemoryDemoStep({ workspaceId }: StepCtx) {
  const [demo, setDemo] = useState<Demo>(FALLBACK);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!workspaceId) {
      setLoading(false);
      return;
    }
    let cancelled = false;
    apiFetch<Demo>(`/api/v1/workspaces/${workspaceId}/memory-demo`, {
      method: "POST",
    })
      .then((d) => {
        if (cancelled) return;
        setDemo(d);
        setLoading(false);
      })
      .catch(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [workspaceId]);

  return (
    <div className="space-y-6">
      <div className="flex items-baseline justify-between gap-3 flex-wrap">
        <h1 className="font-display text-[28px] leading-[1.1] font-bold tracking-tight text-foreground">
          Stop re-explaining yourself
        </h1>
        {demo.real && (
          <span className="text-[10px] font-mono uppercase tracking-wider text-brand">
            Example from your last session
          </span>
        )}
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <Column
          label="Without memory"
          tone="muted"
          steps={demo.before_steps.map((s) => ({ text: s, emphasis: false }))}
          loading={loading}
        />
        <Column
          label="With Stash"
          tone="brand"
          steps={[{ text: demo.after_step, emphasis: true }]}
          loading={loading}
        />
      </div>

      <p className="text-center text-[15px] font-display font-semibold tracking-tight text-foreground pt-2">
        The agent just knows. Like a human would.
      </p>
    </div>
  );
}

type Step = { text: string; emphasis: boolean };

function Column({
  label,
  tone,
  steps,
  loading,
}: {
  label: string;
  tone: "muted" | "brand";
  steps: Step[];
  loading: boolean;
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

      <ol
        className={`relative flex flex-col gap-3 transition-opacity ${
          loading ? "opacity-50" : ""
        }`}
      >
        {steps.map((step, i) => (
          <li key={i} className="relative flex items-start gap-3">
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
              className={`text-[12.5px] leading-relaxed text-foreground ${
                step.emphasis ? "font-medium" : ""
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
