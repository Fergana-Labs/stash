"use client";

import { useState } from "react";
import { ChevronRight, Copy } from "lucide-react";

import { cn } from "@/lib/utils";

import DeveloperGate from "@/components/developer/DeveloperGate";
import { CodeBlock, PageHeading, SectionHeading } from "@/components/developer/DocsPrimitives";
import { BACKFILL_PROMPT, INSTALL_PROMPT } from "@/components/developer/agentPrompts";

export default function DeveloperPrompts() {
  return (
    <DeveloperGate>
      <PageHeading title="Prompts">
        You don&apos;t integrate Stash by hand — your coding agent does. Copy a prompt, drop
        your API key into the first line, and paste it into your agent, pointed at your
        codebase.
      </PageHeading>

      <PromptSection
        title="Install"
        blurb="The whole onboarding in one prompt: the memory read before each turn, the
          transcript upload after it, a backfill of whatever history your database already
          holds, and a final check that a user shows up in this console. Fill in the first
          line with a key from the API Keys page."
        prompt={INSTALL_PROMPT}
      />

      <Advanced>
        <PromptSection
          title="Backfill only"
          blurb="For a stash that is already installed. Install covers your history on the way
            in — reach for this only when there is history left to load: you skipped it
            during install, or you've since imported another database."
          prompt={BACKFILL_PROMPT}
        />
      </Advanced>
    </DeveloperGate>
  );
}

/** Collapsed by default: most developers never need what's inside. */
function Advanced({ children }: { children: React.ReactNode }) {
  const [open, setOpen] = useState(false);

  return (
    <div className="border-t border-border pt-8">
      <button
        onClick={() => setOpen((o) => !o)}
        aria-expanded={open}
        className="flex items-center gap-1.5 font-mono text-[10px] uppercase tracking-[0.2em] text-muted-foreground transition-colors hover:text-foreground"
      >
        <ChevronRight className={cn("h-3 w-3 transition-transform", open && "rotate-90")} />
        Advanced
      </button>
      {open && <div className="mt-6">{children}</div>}
    </div>
  );
}

function PromptSection({
  title,
  blurb,
  prompt,
}: {
  title: string;
  blurb: string;
  prompt: string;
}) {
  const [copied, setCopied] = useState(false);

  function copy() {
    navigator.clipboard.writeText(prompt);
    setCopied(true);
    setTimeout(() => setCopied(false), 1500);
  }

  return (
    <section className="mb-12">
      <div className="flex items-baseline justify-between gap-4">
        <SectionHeading>{title}</SectionHeading>
        <button
          onClick={copy}
          className="flex shrink-0 items-center gap-2 rounded-sm bg-brand-500 px-3 py-1.5 text-[13px] font-medium text-white transition-colors hover:bg-brand-600"
        >
          <Copy className="h-3.5 w-3.5" />
          {copied ? "Copied" : "Copy prompt"}
        </button>
      </div>
      <p className="mt-2 max-w-2xl text-[13.5px] leading-6 text-muted-foreground">{blurb}</p>
      <div className="mt-4">
        <CodeBlock>{prompt}</CodeBlock>
      </div>
    </section>
  );
}
