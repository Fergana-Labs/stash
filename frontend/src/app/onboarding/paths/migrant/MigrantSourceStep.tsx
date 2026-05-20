"use client";

import type { MigrantSource, StepCtx } from "@/lib/onboarding/paths";

type Card = {
  id: MigrantSource;
  title: string;
  pitch: string;
};

const CARDS: Card[] = [
  {
    id: "notion",
    title: "Notion, agent-native",
    pitch:
      "Your pages stay HTML + markdown, in a folder tree your agent can walk directly.",
  },
  {
    id: "obsidian",
    title: "Your vault, collaboratively",
    pitch:
      "Drop your vault — every note becomes a page two people can edit in real time.",
  },
  {
    id: "github",
    title: "GitHub, without the git",
    pitch:
      "We import your repo. No commands. Searchable, editable, with a better editor.",
  },
  {
    id: "drive",
    title: "Drive, but searchable",
    pitch:
      "Pull in your Drive folders and files. Searchable, askable, agent-readable.",
  },
];

export default function MigrantSourceStep({ pickSource }: StepCtx) {
  function pick(id: MigrantSource) {
    pickSource(id);
  }

  return (
    <div className="space-y-6">
      <div className="space-y-2">
        <h1 className="font-display text-[28px] leading-[1.1] font-bold tracking-tight text-foreground">
          Where&rsquo;s your knowledge today?
        </h1>
        <p className="text-sm text-dim max-w-md">
          We&rsquo;ll tailor the next step to your source. All paths bring in
          your agent transcripts and sessions too.
        </p>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {CARDS.map((c) => (
          <button
            key={c.id}
            type="button"
            onClick={() => pick(c.id)}
            className="text-left rounded-2xl border border-border bg-surface p-5 hover:bg-raised hover:border-brand transition-colors flex flex-col gap-3"
          >
            <div className="text-[13px] font-semibold text-foreground">
              {c.title}
            </div>
            <div className="text-[12px] text-muted leading-relaxed">
              {c.pitch}
            </div>
          </button>
        ))}
      </div>

      <p className="text-[11px] text-dim">
        We also bring in your agent transcripts and sessions, regardless of
        which source you pick.
      </p>
    </div>
  );
}
