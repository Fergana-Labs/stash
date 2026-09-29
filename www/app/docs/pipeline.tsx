"use client";

import { useEffect, useState } from "react";

// Each stage opens a short recording of that step in the Stash app, so the
// reader sees the product without leaving the page.
const STAGES = [
  {
    n: "01",
    title: "Import",
    artifact: "traces.jsonl",
    body: "Paste or upload your agent's traces.",
    video: "/docs/demo/import.mp4",
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

type Stage = (typeof STAGES)[number];

export function Pipeline() {
  const [open, setOpen] = useState<Stage | null>(null);

  return (
    <>
      <figure className="my-8 overflow-hidden rounded-2xl border border-border bg-white">
        <div className="grid grid-cols-1 gap-px bg-border-subtle sm:grid-cols-2 lg:grid-cols-4">
          {STAGES.map((s) => (
            <button
              key={s.n}
              type="button"
              onClick={() => setOpen(s)}
              className="group block bg-white px-5 py-5 text-left transition-colors hover:bg-surface"
            >
              <div className="font-mono text-[11px] text-muted">{s.n}</div>
              <div className="mt-1 font-display text-[19px] font-semibold text-ink group-hover:text-brand">
                {s.title}
              </div>
              <div className="mt-3 inline-block rounded-md border border-border-subtle bg-surface px-2 py-1 font-mono text-[12px] text-foreground">
                {s.artifact}
              </div>
              <p className="mt-3 text-[13px] leading-5 text-dim">{s.body}</p>
              <div className="mt-4 inline-flex items-center gap-1.5 text-[12px] font-medium text-muted group-hover:text-brand">
                <PlayIcon />
                Watch
              </div>
            </button>
          ))}
        </div>
      </figure>
      {open && <DemoLightbox stage={open} onClose={() => setOpen(null)} />}
    </>
  );
}

function DemoLightbox({ stage, onClose }: { stage: Stage; onClose: () => void }) {
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    window.addEventListener("keydown", onKey);
    return () => {
      document.body.style.overflow = previousOverflow;
      window.removeEventListener("keydown", onKey);
    };
  }, [onClose]);

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-label={stage.title}
      onClick={onClose}
      className="fixed inset-0 z-50 flex items-center justify-center bg-ink/60 p-4 backdrop-blur-sm sm:p-8"
    >
      <div
        onClick={(e) => e.stopPropagation()}
        className="w-full max-w-[min(1100px,calc((100vh-9rem)*1.6))] overflow-hidden rounded-2xl border border-border bg-white shadow-2xl"
      >
        <div className="flex items-center justify-between border-b border-border-subtle px-5 py-3">
          <div className="flex items-baseline gap-3">
            <span className="font-mono text-[11px] text-muted">{stage.n}</span>
            <span className="font-display text-[17px] font-semibold text-ink">{stage.title}</span>
            <span className="hidden text-[13px] text-dim sm:inline">{stage.body}</span>
          </div>
          <button
            type="button"
            onClick={onClose}
            aria-label="Close"
            className="rounded-md px-2 py-1 text-[20px] leading-none text-muted hover:bg-surface hover:text-ink"
          >
            ×
          </button>
        </div>
        <video
          key={stage.video}
          src={stage.video}
          autoPlay
          loop
          muted
          playsInline
          className="block aspect-[8/5] w-full bg-surface"
        />
      </div>
    </div>
  );
}

function PlayIcon() {
  return (
    <svg width="10" height="10" viewBox="0 0 10 10" aria-hidden="true">
      <path d="M2 1.2v7.6L8.6 5 2 1.2z" fill="currentColor" />
    </svg>
  );
}
