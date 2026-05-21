"use client";

import type { ComponentType } from "react";

import {
  GitHubIcon,
  GoogleDriveIcon,
  NotionIcon,
  ObsidianIcon,
} from "@/components/integrations/BrandIcons";
import type { MigrantSource, StepCtx } from "@/lib/onboarding/paths";

type Card = {
  id: MigrantSource;
  title: string;
  pitch: string;
  Icon: ComponentType<{ className?: string; size?: number }>;
  // Tailwind classes for the icon background tile.
  iconClass: string;
};

const CARDS: Card[] = [
  {
    id: "notion",
    title: "Notion, agent-native",
    pitch:
      "Your content stays HTML + markdown, in a folder tree your agent can walk directly.",
    Icon: NotionIcon,
    iconClass: "bg-foreground/5 text-foreground",
  },
  {
    id: "obsidian",
    title: "Your vault, collaboratively",
    pitch:
      "Drop your vault — every note becomes collaboratively editable in real time.",
    Icon: ObsidianIcon,
    iconClass: "bg-violet-500/10",
  },
  {
    id: "github",
    title: "GitHub, without the git",
    pitch:
      "We import your repo. No commands. Searchable, editable, with a better editor.",
    Icon: GitHubIcon,
    iconClass: "bg-foreground/5 text-foreground",
  },
  {
    id: "drive",
    title: "Drive, but searchable",
    pitch:
      "Pull in your Drive folders and docs. Searchable, askable, agent-readable.",
    Icon: GoogleDriveIcon,
    iconClass: "bg-blue-500/10",
  },
];

export default function MigrantSourceStep({ pickSource }: StepCtx) {
  function pick(id: MigrantSource) {
    pickSource(id);
  }

  return (
    <div className="space-y-6">
      <h1 className="font-display text-[28px] leading-[1.1] font-bold tracking-tight text-foreground">
        Where&rsquo;s your knowledge today?
      </h1>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {CARDS.map((c) => (
          <button
            key={c.id}
            type="button"
            onClick={() => pick(c.id)}
            className="text-left rounded-2xl border border-border bg-surface p-5 hover:bg-raised hover:border-brand transition-colors flex flex-col gap-3"
          >
            <span
              aria-hidden
              className={`flex h-10 w-10 items-center justify-center rounded-lg ${c.iconClass}`}
            >
              <c.Icon size={22} />
            </span>
            <div className="text-[13px] font-semibold text-foreground">
              {c.title}
            </div>
            <div className="text-[12px] text-muted leading-relaxed">
              {c.pitch}
            </div>
          </button>
        ))}
      </div>

      <p className="text-[11.5px] text-dim">
        Pick one to start — your agent transcripts flow in automatically
        once you install the CLI at the end.
      </p>
    </div>
  );
}
