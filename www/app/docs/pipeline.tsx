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
    artifact: "comments · corrections",
    body: "Highlight what went wrong and say why.",
    video: "/docs/demo/annotate.mp4",
  },
  {
    n: "03",
    title: "Train",
    artifact: "reward model",
    body: "Supported feedback becomes training pairs.",
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

// The recordings are real-time; at 3x the four steps cycle in about 20 seconds.
const PLAYBACK_RATE = 3;

export function Pipeline() {
  // The recordings play through in order on their own, so a reader sees the
  // whole flow without clicking. Closing the open card stops the cycle.
  const [openN, setOpenN] = useState<string | null>(STAGES[0].n);
  const [progress, setProgress] = useState(0);
  const open = STAGES.find((s) => s.n === openN);

  function select(n: string | null) {
    setProgress(0);
    setOpenN(n);
  }

  function playNext() {
    const index = STAGES.findIndex((s) => s.n === openN);
    select(STAGES[(index + 1) % STAGES.length].n);
  }

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
              onClick={() => select(isOpen ? null : s.n)}
              className={`group relative flex h-full flex-col items-start justify-start px-5 py-5 text-left transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-brand/40 ${
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
              {isOpen && (
                <div className="absolute inset-x-0 bottom-0 h-[3px] bg-border-subtle">
                  <div
                    className="h-full bg-brand transition-[width] duration-200 ease-linear"
                    style={{ width: `${progress * 100}%` }}
                  />
                </div>
              )}
            </button>
          );
        })}
      </div>
      {open && (
        <video
          key={open.video}
          src={open.video}
          autoPlay
          muted
          playsInline
          ref={(video) => {
            // Set on mount: the first clip's metadata can load before React hydrates,
            // so a loadedmetadata handler would miss it.
            if (!video) return;
            video.defaultPlaybackRate = PLAYBACK_RATE;
            video.playbackRate = PLAYBACK_RATE;
          }}
          onTimeUpdate={(e) => setProgress(e.currentTarget.currentTime / e.currentTarget.duration)}
          onEnded={playNext}
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
