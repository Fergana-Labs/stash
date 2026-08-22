"use client";

import { useState } from "react";
import { Copy } from "lucide-react";

import DeveloperGate from "@/components/developer/DeveloperGate";
import { CodeBlock, PageHeading } from "@/components/developer/DocsPrimitives";

/** One console prompt page: what the prompt does, a copy button, and the
 *  prompt itself. The reader never runs these — their coding agent does. */
export default function PromptPage({
  title,
  blurb,
  prompt,
}: {
  title: string;
  blurb: React.ReactNode;
  prompt: string;
}) {
  const [copied, setCopied] = useState(false);

  function copy() {
    navigator.clipboard.writeText(prompt);
    setCopied(true);
    setTimeout(() => setCopied(false), 1500);
  }

  return (
    <DeveloperGate>
      <div className="flex items-start justify-between gap-4">
        <PageHeading title={title}>{blurb}</PageHeading>
        <button
          onClick={copy}
          className="mt-2 flex shrink-0 items-center gap-2 rounded-sm bg-brand-500 px-3.5 py-2 text-[13px] font-medium text-white transition-colors hover:bg-brand-600"
        >
          <Copy className="h-3.5 w-3.5" />
          {copied ? "Copied" : "Copy prompt"}
        </button>
      </div>
      <CodeBlock>{prompt}</CodeBlock>
    </DeveloperGate>
  );
}
