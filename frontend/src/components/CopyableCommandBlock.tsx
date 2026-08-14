"use client";

import { useState } from "react";
import { Check, Copy } from "lucide-react";
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
      <pre className="whitespace-pre-wrap break-all rounded-md border border-border bg-surface px-3 py-2.5 pr-10 font-mono text-[11.5px] leading-relaxed text-foreground">
        {commands}
      </pre>
      {/* Icon-only, so a long command keeps as much width as possible and the
          block reads as code rather than as a form control. */}
      <button
        type="button"
        onClick={() => void copy()}
        aria-label={copied ? "Copied" : "Copy to clipboard"}
        title={copied ? "Copied" : "Copy"}
        className="absolute right-1.5 top-1.5 cursor-pointer rounded p-1.5 text-muted-foreground transition-colors hover:bg-raised hover:text-foreground"
      >
        {copied ? <Check className="h-3.5 w-3.5 text-success" /> : <Copy className="h-3.5 w-3.5" />}
      </button>
    </div>
  );
}
