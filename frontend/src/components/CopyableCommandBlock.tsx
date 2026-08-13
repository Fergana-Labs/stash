"use client";

import { useState } from "react";

const COPIED_RESET_MS = 1500;

// A quiet terminal-command snippet with a copy button, used by empty-state
// CTAs that ask the user to run something in their terminal.
export default function CopyableCommandBlock({ commands }: { commands: string }) {
  const [copied, setCopied] = useState(false);

  async function copy() {
    await navigator.clipboard.writeText(commands);
    setCopied(true);
    setTimeout(() => setCopied(false), COPIED_RESET_MS);
  }

  return (
    <div className="relative inline-block max-w-full text-left">
      {/* Wrap rather than scroll: a scrolling line slides underneath the
          absolutely-positioned copy button, which reads as broken in a narrow
          container like a dialog. */}
      <pre className="whitespace-pre-wrap break-all rounded-md border border-border bg-surface px-3 py-2 pr-16 font-mono text-[11.5px] leading-relaxed text-foreground">
        {commands}
      </pre>
      <button
        type="button"
        onClick={() => void copy()}
        className="absolute right-1.5 top-1.5 cursor-pointer rounded border border-border bg-base px-1.5 py-0.5 text-[10.5px] font-medium text-muted-foreground hover:text-foreground"
      >
        {copied ? "Copied" : "Copy"}
      </button>
    </div>
  );
}
