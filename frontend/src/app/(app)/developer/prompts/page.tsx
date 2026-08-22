"use client";

import { useState } from "react";
import { ChevronRight, Copy } from "lucide-react";

import { cn } from "@/lib/utils";

import DeveloperGate from "@/components/developer/DeveloperGate";
import { CodeBlock, PageHeading, SectionHeading } from "@/components/developer/DocsPrimitives";
import { BACKFILL_PROMPT, INSTALL_PROMPT, KEY_PLACEHOLDER } from "@/components/developer/agentPrompts";

export default function DeveloperPrompts() {
  const [apiKey, setApiKey] = useState("");
  const installPrompt = apiKey.trim()
    ? INSTALL_PROMPT.replace(KEY_PLACEHOLDER, apiKey.trim())
    : INSTALL_PROMPT;

  return (
    <DeveloperGate>
      <PageHeading title="Prompts">
        You don&apos;t integrate Stash by hand — your coding agent does. Paste your API key
        into the first line, copy the prompt, and paste it into your agent, pointed at your
        codebase.
      </PageHeading>

      <PromptSection
        title="Install"
        blurb="The whole onboarding in one prompt: the memory read before each turn, the
          transcript upload after it, a backfill of whatever history your database already
          holds, and a final check that a user shows up in this console. Paste a key from
          the API Keys page into the first line."
        prompt={installPrompt}
        keyField={{ value: apiKey, onChange: setApiKey }}
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
  keyField,
}: {
  title: string;
  blurb: string;
  prompt: string;
  // When set, the prompt's first line renders as "MY API KEY IS" plus this
  // editable field, so a key on the clipboard can go straight in. The key
  // lives only in component state — never persisted.
  keyField?: { value: string; onChange: (value: string) => void };
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
        {keyField ? (
          <div className="overflow-x-auto rounded border border-border bg-surface p-5 font-mono text-[12.5px] leading-6 text-dim">
            <div className="flex items-center gap-2 whitespace-pre">
              <span>MY API KEY IS</span>
              <input
                value={keyField.value}
                onChange={(e) => keyField.onChange(e.target.value)}
                placeholder={KEY_PLACEHOLDER}
                aria-label="API key"
                spellCheck={false}
                autoComplete="off"
                className="min-w-64 flex-1 rounded-sm border border-dashed border-border bg-base px-2 py-0.5 font-mono text-[12.5px] text-foreground placeholder:text-muted-foreground focus:border-solid focus:border-brand-500 focus:outline-none"
              />
            </div>
            <pre className="m-0 whitespace-pre-wrap">
              <code>{prompt.split("\n").slice(1).join("\n")}</code>
            </pre>
          </div>
        ) : (
          <CodeBlock>{prompt}</CodeBlock>
        )}
      </div>
    </section>
  );
}
