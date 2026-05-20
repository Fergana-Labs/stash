"use client";

import Link from "next/link";

type Props = {
  workspaceId: string | null;
};

export default function DoneStep({ workspaceId }: Props) {
  return (
    <div className="space-y-6">
      <div className="space-y-2">
        <h1 className="font-display text-[28px] leading-[1.1] font-bold tracking-tight text-foreground">
          You&rsquo;re set up
        </h1>
        <p className="text-sm text-dim max-w-md">
          Two things you might want next.
        </p>
      </div>

      <div className="rounded-2xl border border-border bg-surface p-5 space-y-2">
        <div className="text-[13px] font-semibold text-foreground">
          Install the CLI for the full integration
        </div>
        <p className="text-[12px] text-muted leading-relaxed">
          The CLI lets your agent push session transcripts automatically and
          gives you{" "}
          <code className="text-foreground">stash share</code>,{" "}
          <code className="text-foreground">stash discover</code>, and more.
        </p>
        <pre className="rounded-md border border-border-subtle bg-background/40 px-3 py-2 text-[12px] font-mono text-foreground overflow-x-auto">
          npm i -g @joinstash/cli
        </pre>
        <Link
          href="/docs/cli"
          className="inline-block text-[12px] font-medium text-brand hover:text-brand-hover"
        >
          CLI docs →
        </Link>
      </div>

      <div className="rounded-2xl border border-border bg-surface p-5 space-y-2">
        <div className="text-[13px] font-semibold text-foreground">
          Go to your workspace
        </div>
        <p className="text-[12px] text-muted leading-relaxed">
          Open the workspace home — anything you shared, imported, or copied
          in is already there.
        </p>
        {workspaceId && (
          <Link
            href={`/workspaces/${workspaceId}`}
            className="inline-block rounded-md bg-brand px-4 py-2 text-[12px] font-medium text-white hover:bg-brand-hover transition-colors"
          >
            Open workspace
          </Link>
        )}
      </div>
    </div>
  );
}
