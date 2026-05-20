"use client";

import type { StepCtx } from "@/lib/onboarding/paths";

export default function MigrantDemoStep({ source }: StepCtx) {
  return (
    <div className="space-y-6">
      <div className="space-y-2">
        <h1 className="font-display text-[28px] leading-[1.1] font-bold tracking-tight text-foreground">
          What just got better
        </h1>
        <p className="text-sm text-dim max-w-md">
          Your import is running in the background. Here&rsquo;s what changes
          once it lands.
        </p>
      </div>

      {source === "notion" && <NotionDemo />}
      {source === "obsidian" && <ObsidianDemo />}
      {source === "github" && <GithubDemo />}
      {source === "drive" && <DriveDemo />}
      {!source && (
        <div className="text-sm text-muted">No source picked — skip ahead.</div>
      )}
    </div>
  );
}

function DemoFrame({
  leftTitle,
  leftBody,
  rightTitle,
  rightBody,
  tagline,
}: {
  leftTitle: string;
  leftBody: React.ReactNode;
  rightTitle: string;
  rightBody: React.ReactNode;
  tagline: string;
}) {
  return (
    <div className="space-y-3">
      <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
        <div className="rounded-xl border border-border-subtle bg-background/40 p-4 space-y-2 min-h-[180px]">
          <div className="text-[11px] font-mono uppercase tracking-wider text-muted">
            {leftTitle}
          </div>
          <div className="text-[12px] text-foreground leading-relaxed">{leftBody}</div>
        </div>
        <div className="rounded-xl border border-brand bg-brand/5 p-4 space-y-2 min-h-[180px]">
          <div className="text-[11px] font-mono uppercase tracking-wider text-brand">
            {rightTitle}
          </div>
          <div className="text-[12px] text-foreground leading-relaxed">{rightBody}</div>
        </div>
      </div>
      <div className="text-[13px] font-medium text-foreground">{tagline}</div>
    </div>
  );
}

function NotionDemo() {
  return (
    <DemoFrame
      leftTitle="In Notion"
      leftBody={
        <ul className="font-mono text-[11.5px] leading-snug space-y-0.5">
          <li>📄 Engineering wiki</li>
          <li className="pl-4">📄 Onboarding</li>
          <li className="pl-4">📄 API gateway runbook</li>
          <li>📄 Sprint notes</li>
          <li className="pl-4">📄 2026-05-13</li>
        </ul>
      }
      rightTitle="Here, agent-readable"
      rightBody={
        <div className="space-y-2">
          <ul className="font-mono text-[11.5px] leading-snug space-y-0.5">
            <li>📁 engineering-wiki/</li>
            <li className="pl-4">📄 onboarding.md</li>
            <li className="pl-4">📄 api-gateway-runbook.md</li>
            <li>📁 sprint-notes/</li>
            <li className="pl-4">📄 2026-05-13.md</li>
          </ul>
          <div className="text-[11px] text-muted italic">
            Your agent can walk this tree directly. No copy/paste.
          </div>
        </div>
      }
      tagline="Notion pages without the API hoops."
    />
  );
}

function ObsidianDemo() {
  return (
    <DemoFrame
      leftTitle="In Obsidian"
      leftBody={
        <div className="space-y-1.5">
          <div className="font-mono text-[11.5px] text-foreground">
            # API gateway runbook
          </div>
          <div className="font-mono text-[11px] text-muted">
            Cursor: <span className="text-foreground">you</span>
          </div>
          <div className="text-[11px] text-muted italic mt-2">
            One person at a time. Sync via iCloud, hope for no conflicts.
          </div>
        </div>
      }
      rightTitle="Here, two cursors"
      rightBody={
        <div className="space-y-1.5">
          <div className="font-mono text-[11.5px] text-foreground">
            # API gateway runbook
          </div>
          <div className="font-mono text-[11px]">
            <span className="text-muted">Cursors: </span>
            <span className="text-brand">you</span>
            <span className="text-muted"> · </span>
            <span className="text-foreground">teammate</span>
          </div>
          <div className="text-[11px] text-muted italic mt-2">
            Real-time CRDT collab on every markdown page.
          </div>
        </div>
      }
      tagline="What you can't do in Obsidian."
    />
  );
}

function DriveDemo() {
  return (
    <DemoFrame
      leftTitle="In Drive"
      leftBody={
        <div className="space-y-1.5">
          <ul className="font-mono text-[11.5px] leading-snug space-y-0.5">
            <li>📁 Team docs</li>
            <li className="pl-4">📄 Q2 strategy (Google Doc)</li>
            <li className="pl-4">📊 Roadmap (Sheet)</li>
            <li>📁 Engineering</li>
            <li className="pl-4">📄 Architecture overview</li>
          </ul>
          <div className="text-[11px] text-muted italic mt-2">
            Search is brittle. Sharing is per-link. Your agent can&rsquo;t read any
            of it.
          </div>
        </div>
      }
      rightTitle="Here, fully indexed"
      rightBody={
        <div className="space-y-2">
          <ul className="font-mono text-[11.5px] leading-snug space-y-0.5">
            <li>📁 team-docs/</li>
            <li className="pl-4">📄 q2-strategy.md</li>
            <li className="pl-4">📊 roadmap (Table)</li>
            <li>📁 engineering/</li>
            <li className="pl-4">📄 architecture-overview.md</li>
          </ul>
          <div className="text-[11px] text-muted italic">
            Full-text search. Agent-readable. Same content, useful.
          </div>
        </div>
      }
      tagline="Drive content your agent can actually use."
    />
  );
}

function GithubDemo() {
  return (
    <DemoFrame
      leftTitle="With git"
      leftBody={
        <pre className="font-mono text-[11px] text-muted leading-snug whitespace-pre-wrap">{`$ git pull
$ vim docs/runbook.md
$ git add docs/runbook.md
$ git commit -m "edit"
$ git push`}</pre>
      }
      rightTitle="Here"
      rightBody={
        <div className="space-y-2">
          <div className="rounded-md border border-border-subtle bg-background/60 p-2">
            <div className="flex items-center justify-between text-[10px] text-muted mb-1">
              <span>docs/runbook.md</span>
              <span>Synced 12s ago</span>
            </div>
            <div className="font-mono text-[11px] text-foreground">
              # Runbook<br />Click. Edit. Done.
            </div>
          </div>
          <div className="rounded-md border border-border-subtle bg-background/60 p-1.5 flex items-center gap-2">
            <span className="text-[11px] text-muted">🔍</span>
            <span className="font-mono text-[11px] text-foreground">
              quic
              <span className="bg-brand/30">k matches in 3 files</span>
            </span>
          </div>
        </div>
      }
      tagline="Same repo, without the commands."
    />
  );
}
