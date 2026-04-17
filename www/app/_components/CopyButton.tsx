"use client";

import { useState } from "react";

type Props = {
  value: string;
  label?: string;
  copiedLabel?: string;
};

export default function CopyButton({
  value,
  label = "Copy",
  copiedLabel = "Copied",
}: Props) {
  const [copied, setCopied] = useState(false);

  async function handleCopy() {
    try {
      await navigator.clipboard.writeText(value);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      // Clipboard blocked (no https, denied perms). User can still select + copy.
    }
  }

  return (
    <button
      type="button"
      onClick={handleCopy}
      className="inline-flex h-10 items-center rounded-md bg-brand px-4 text-[14px] font-medium text-white transition hover:bg-brand-hover"
    >
      {copied ? copiedLabel : label}
    </button>
  );
}
