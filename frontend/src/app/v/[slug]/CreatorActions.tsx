"use client";

import Link from "next/link";
import { useAuth } from "../../../hooks/useAuth";

const MARKETING_URL = process.env.NEXT_PUBLIC_MARKETING_URL || "https://joinstash.ai";

type Props = {
  ownerId: string;
  workspaceId: string;
};

export default function CreatorActions({ ownerId, workspaceId }: Props) {
  const { user, loading } = useAuth();
  if (loading || !user || user.id !== ownerId) return null;

  return (
    <aside className="mt-12 rounded-2xl border border-border bg-surface p-6 space-y-5">
      <div className="space-y-1.5">
        <p className="font-mono text-[11px] uppercase tracking-wider text-brand">
          You shipped one. Now make it shared.
        </p>
        <h2 className="font-display text-[20px] font-bold text-ink leading-tight">
          Don&rsquo;t leave your agent&rsquo;s work in scattered URLs.
        </h2>
        <p className="text-[13px] text-dim leading-relaxed max-w-[560px]">
          Pull every page, transcript, and artifact your agents make into one space
          you and your team can browse, search, and build on.
        </p>
      </div>

      <ol className="space-y-3">
        <li>
          <Link
            href={`/stashes/${workspaceId}?invite=open`}
            className="group flex items-start gap-3 rounded-xl border border-border-subtle bg-background/40 hover:border-brand/60 hover:bg-background/60 transition-colors px-4 py-3"
          >
            <span className="shrink-0 inline-flex items-center justify-center w-6 h-6 rounded-full bg-brand/10 text-brand text-[11px] font-mono font-semibold">
              1
            </span>
            <span className="flex-1 min-w-0">
              <span className="block text-[13px] font-medium text-foreground group-hover:text-brand transition-colors">
                Share with a teammate &mdash; turn this into a Stash
              </span>
              <span className="block text-[12px] text-muted mt-0.5">
                Invite someone in. The page becomes part of a shared, ongoing space
                instead of a one-off URL.
              </span>
            </span>
            <Arrow />
          </Link>
        </li>
        <li>
          <a
            href={`${MARKETING_URL}/docs/quickstart?from=creator-cta`}
            target="_blank"
            rel="noreferrer"
            className="group flex items-start gap-3 rounded-xl border border-border-subtle bg-background/40 hover:border-brand/60 hover:bg-background/60 transition-colors px-4 py-3"
          >
            <span className="shrink-0 inline-flex items-center justify-center w-6 h-6 rounded-full bg-brand/10 text-brand text-[11px] font-mono font-semibold">
              2
            </span>
            <span className="flex-1 min-w-0">
              <span className="block text-[13px] font-medium text-foreground group-hover:text-brand transition-colors">
                Install the CLI for the full integration
              </span>
              <span className="block text-[12px] text-muted mt-0.5">
                Drop the curl &mdash; let your agent publish via MCP, and stream
                every session into the same space.
              </span>
            </span>
            <Arrow />
          </a>
        </li>
      </ol>
    </aside>
  );
}

function Arrow() {
  return (
    <svg
      className="shrink-0 mt-0.5 text-muted group-hover:text-brand transition-colors"
      width="16"
      height="16"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      <path d="M5 12h14M13 5l7 7-7 7" />
    </svg>
  );
}
