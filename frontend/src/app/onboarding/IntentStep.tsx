"use client";

import IosShareOutlinedIcon from "@mui/icons-material/IosShareOutlined";
import MenuBookOutlinedIcon from "@mui/icons-material/MenuBookOutlined";
import PsychologyOutlinedIcon from "@mui/icons-material/PsychologyOutlined";
import type { ComponentType } from "react";

import type { PathId } from "@/lib/onboarding/paths";

type Props = {
  onPick: (path: PathId) => void;
};

type Option = {
  id: PathId;
  Icon: ComponentType<{ className?: string; fontSize?: "inherit" }>;
  title: string;
  blurb: string;
  examples?: string;
};

const OPTIONS: Option[] = [
  {
    id: "migrant",
    Icon: MenuBookOutlinedIcon,
    title: "I already use a knowledge base",
    blurb:
      "Bring your existing docs over and see how they work better here, alongside your agent sessions.",
    examples: "Notion · Obsidian · GitHub · Google Drive",
  },
  {
    id: "memory",
    Icon: PsychologyOutlinedIcon,
    title: "I want better memory for my AI agents",
    blurb:
      "Bring in your past agent sessions so the next conversation isn't starting from scratch. Your agent remembers what you've worked on.",
  },
  {
    id: "sharing",
    Icon: IosShareOutlinedIcon,
    title: "I want to collaborate on agent artifacts",
    blurb:
      "Share session transcripts, agent-generated HTML, markdown — anyone with the link can view. No setup, no CLI.",
  },
];

export default function IntentStep({ onPick }: Props) {
  return (
    <div className="min-h-[70vh] flex flex-col items-center justify-center px-4 py-12">
      <div className="w-full max-w-3xl space-y-10">
        <div className="space-y-3 text-center">
          <div className="flex flex-col items-center gap-2">
            {/* eslint-disable-next-line @next/next/no-img-element -- raw SVG, no need for next/image optimization */}
            <img
              src="/octopus.svg"
              alt="Stash"
              className="h-14 w-14"
            />
            <div className="text-[12px] font-mono uppercase tracking-[0.18em] text-muted">
              Welcome to Stash
            </div>
          </div>
          <h1 className="font-display text-[36px] leading-[1.05] font-bold tracking-tight text-foreground">
            What brought you here?
          </h1>
          <p className="text-sm text-dim max-w-md mx-auto">
            Pick the path that fits — we&rsquo;ll tailor the rest of onboarding
            to it.
          </p>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          {OPTIONS.map((opt) => (
            <button
              key={opt.id}
              type="button"
              onClick={() => onPick(opt.id)}
              className="text-left rounded-2xl border border-border bg-surface p-5 hover:bg-raised hover:border-brand transition-colors flex flex-col gap-3"
            >
              <span
                aria-hidden
                className="flex h-9 w-9 items-center justify-center rounded-lg bg-brand/10 text-brand text-[22px]"
              >
                <opt.Icon fontSize="inherit" />
              </span>
              <div className="text-[14px] font-semibold text-foreground leading-snug">
                {opt.title}
              </div>
              <div className="text-[12.5px] text-muted leading-relaxed">
                {opt.blurb}
              </div>
              {opt.examples && (
                <div className="text-[11px] font-mono uppercase tracking-wider text-dim mt-auto">
                  {opt.examples}
                </div>
              )}
            </button>
          ))}
        </div>
      </div>
    </div>
  );
}
