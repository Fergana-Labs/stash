"use client";

import Link from "next/link";

import type { StepCtx } from "@/lib/onboarding/paths";

export default function MemorySearchStep({ workspaceId }: StepCtx) {
  const searchHref = workspaceId
    ? `/search?workspace=${workspaceId}`
    : "/search";

  return (
    <div className="space-y-6">
      <div className="space-y-2">
        <h1 className="font-display text-[28px] leading-[1.1] font-bold tracking-tight text-foreground">
          Every past session, searchable
        </h1>
        <p className="text-sm text-dim max-w-md">
          Full-text search across every session transcript, page, file, and
          table in your workspace.
        </p>
      </div>

      <div className="rounded-2xl border border-border bg-surface p-5 space-y-4">
        <div className="flex items-center gap-2 rounded-md border border-border-subtle bg-background/40 px-3 py-2">
          <span className="text-muted">🔍</span>
          <input
            type="search"
            placeholder="Try a query — e.g. authentication, rate limiting…"
            className="flex-1 bg-transparent text-[13px] text-foreground placeholder:text-muted focus:outline-none"
            readOnly
            onFocus={(e) => {
              e.currentTarget.blur();
              if (typeof window !== "undefined") {
                window.location.href = searchHref;
              }
            }}
          />
        </div>
        <Link
          href={searchHref}
          className="inline-block rounded-md bg-brand px-4 py-2 text-[13px] font-medium text-white hover:bg-brand-hover"
        >
          Open search →
        </Link>
        <p className="text-[11.5px] text-muted leading-relaxed">
          Search opens in a new tab — come back here when you&rsquo;re done to
          finish setup.
        </p>
      </div>
    </div>
  );
}
