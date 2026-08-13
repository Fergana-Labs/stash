"use client";

import { useState } from "react";
import { toast } from "sonner";

const COPIED_RESET_MS = 1500;

// A quiet terminal-command snippet with a copy button, used by empty-state
// CTAs that ask the user to run something in their terminal.
export default function CopyableCommandBlock({ commands }: { commands: string }) {
  const [copied, setCopied] = useState(false);

  // The Clipboard API rejects for reasons the page can't prevent — a denied
  // permission, an unfocused document, an embedded context. Unhandled, the
  // button just does nothing and the user has no idea the copy failed.
  async function copy() {
    try {
      await navigator.clipboard.writeText(commands);
    } catch {
      toast.error("Couldn't copy — select the command and copy it manually.");
      return;
    }
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
