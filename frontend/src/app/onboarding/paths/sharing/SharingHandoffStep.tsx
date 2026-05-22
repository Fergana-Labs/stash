"use client";

import Link from "next/link";

export default function SharingHandoffStep() {
  return (
    <div className="space-y-6">
      <div>
        <h1 className="font-display text-[28px] leading-[1.1] font-bold tracking-tight text-foreground">
          Keep going from your agent
        </h1>
      </div>

      <div className="rounded-2xl border border-border bg-surface p-5 space-y-3">
        <div className="text-[13px] font-semibold text-foreground">
          Install the CLI
        </div>
        <p className="text-[12.5px] text-muted leading-relaxed">
          One command. First run pops a browser window and signs you in
          automatically — no API key to copy around.
        </p>
        <pre className="rounded-md border border-border-subtle bg-background/40 px-3 py-2 text-[12px] font-mono text-foreground overflow-x-auto">
          pip install stashai
        </pre>
        <p className="text-[11.5px] text-muted leading-relaxed">
          Need a raw API key for a different setup? Mint one anytime from{" "}
          <Link
            href="/settings"
            className="text-brand hover:text-brand-hover underline"
          >
            Settings
          </Link>
          .
        </p>
      </div>
    </div>
  );
}
