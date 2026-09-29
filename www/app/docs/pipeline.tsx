"use client";

import { useState } from "react";

// Each stage expands a short recording of that step in the Stash app below
// the cards, so the reader sees the product without leaving the page.
const STAGES = [
  {
    n: "01",
    title: "Connect",
    artifact: "OpenTelemetry",
    body: "Your agent's runs stream into Stash.",
    video: "/docs/demo/connect.mp4",
  },
  {
    n: "02",
    title: "Annotate",
    artifact: "+ / − · comment",
    body: "Highlight what went wrong and say why.",
    video: "/docs/demo/annotate.mp4",
  },
  {
    n: "03",
    title: "Train",
    artifact: "reward model",
    body: "Your labels become a reward model.",
    video: "/docs/demo/train.mp4",
  },
  {
    n: "04",
    title: "Write a skill",
    artifact: "SKILL.md",
    body: "GEPA writes a skill your agent loads.",
    video: "/docs/demo/skill.mp4",
  },
];

export function Pipeline() {
  const [openN, setOpenN] = useState<string | null>(null);
  const open = STAGES.find((s) => s.n === openN);

  return (
    <figure className="my-8 overflow-hidden rounded-2xl border border-border bg-white">
      <div className="grid grid-cols-1 gap-px bg-border-subtle sm:grid-cols-2 lg:grid-cols-4">
        {STAGES.map((s) => {
          const isOpen = s.n === openN;
          return (
            <button
              key={s.n}
              type="button"
              aria-expanded={isOpen}
              onClick={() => setOpenN(isOpen ? null : s.n)}
              className={`group flex h-full flex-col items-start justify-start px-5 py-5 text-left transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-brand/40 ${
                isOpen ? "bg-surface" : "bg-white hover:bg-surface"
              }`}
            >
              <div className="font-mono text-[11px] text-muted">{s.n}</div>
              <div
                className={`mt-1 font-display text-[19px] font-semibold group-hover:text-brand ${
                  isOpen ? "text-brand" : "text-ink"
                }`}
              >
                {s.title}
              </div>
              <div className="mt-3 inline-block rounded-md border border-border-subtle bg-surface px-2 py-1 font-mono text-[12px] text-foreground">
                {s.artifact}
              </div>
              <p className="mt-3 text-[13px] leading-5 text-dim">{s.body}</p>
              <div
                className={`mt-4 inline-flex items-center gap-1.5 text-[12px] font-medium group-hover:text-brand ${
                  isOpen ? "text-brand" : "text-muted"
                }`}
              >
                <PlayIcon />
                {isOpen ? "Hide" : "Watch"}
              </div>
            </button>
          );
        })}
      </div>
      {open && (
        <video
          key={open.video}
          src={open.video}
          autoPlay
          loop
          muted
          playsInline
          className="block aspect-[8/5] w-full border-t border-border-subtle bg-surface"
        />
      )}
    </figure>
  );
}

function PlayIcon() {
  return (
    <svg width="10" height="10" viewBox="0 0 10 10" aria-hidden="true">
      <path d="M2 1.2v7.6L8.6 5 2 1.2z" fill="currentColor" />
    </svg>
  );
}
