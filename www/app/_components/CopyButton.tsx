"use client";

import { useState } from "react";

type Props = {
  value: string;
  label?: string;
  copiedLabel?: string;
  className?: string;
};

const DEFAULT_CLASS =
  "inline-flex h-10 items-center rounded-md bg-brand px-4 text-[14px] font-medium text-white transition hover:bg-brand-hover";

export default function CopyButton({
  value,
  label = "Copy",
  copiedLabel = "Copied",
  className = DEFAULT_CLASS,
}: Props) {
  const [copied, setCopied] = useState(false);

  async function handleCopy() {
    try {
      await navigator.clipboard.writeText(value);
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch {
      // Clipboard blocked (no https, denied perms). User can still select + copy.
    }
  }

  return (
    <button type="button" onClick={handleCopy} className={className} data-copied={copied}>
      {copied ? copiedLabel : label}
    </button>
  );
}
