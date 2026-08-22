"use client";

import { useState } from "react";
import { Copy } from "lucide-react";

import DeveloperGate from "@/components/developer/DeveloperGate";
import { CodeBlock, PageHeading, SectionHeading } from "@/components/developer/DocsPrimitives";
import { BACKFILL_PROMPT, INSTALL_PROMPT } from "@/components/developer/agentPrompts";

export default function DeveloperPrompts() {
  return (
    <DeveloperGate>
      <PageHeading title="Prompts">
        You don&apos;t integrate Stash by hand — your coding agent does. Paste one of these
        into it, pointed at your codebase. Mint a key first and put it in your env.
      </PageHeading>

      <PromptSection
        title="Install"
        blurb="The whole onboarding in one prompt: the memory read before each turn, the
          transcript upload after it, a backfill of whatever history your database already
          holds, and a final check that a user shows up in this console."
        prompt={INSTALL_PROMPT}
      />

      <div className="mb-6 border-t border-border pt-8 font-mono text-[10px] uppercase tracking-[0.2em] text-muted-foreground">
        Advanced
      </div>

      <PromptSection
        title="Backfill only"
        blurb="For a stash that is already installed. Install covers your history on the way
          in — reach for this only when there is history left to load: you skipped it
          during install, or you've since imported another database."
        prompt={BACKFILL_PROMPT}
      />
    </DeveloperGate>
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
