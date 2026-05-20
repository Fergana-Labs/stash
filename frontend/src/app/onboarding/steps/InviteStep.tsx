"use client";

import { useEffect, useState } from "react";

import { getWorkspace } from "@/lib/api";

const APP_URL =
  typeof window !== "undefined" ? window.location.origin : "";

type Props = {
  workspaceId: string | null;
};

export default function InviteStep({ workspaceId }: Props) {
  const [inviteCode, setInviteCode] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    if (!workspaceId) return;
    getWorkspace(workspaceId)
      .then((ws) => setInviteCode(ws.invite_code))
      .catch((e) => setError(e instanceof Error ? e.message : String(e)));
  }, [workspaceId]);

  const inviteUrl = inviteCode ? `${APP_URL}/join/${inviteCode}` : "";

  async function handleCopy() {
    if (!inviteUrl) return;
    await navigator.clipboard.writeText(inviteUrl);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  }

  return (
    <div className="space-y-6">
      <div className="space-y-2">
        <h1 className="font-display text-[28px] leading-[1.1] font-bold tracking-tight text-foreground">
          Invite teammates
        </h1>
        <p className="text-sm text-dim max-w-md">
          Send this link to anyone you want in your workspace. They&rsquo;ll
          join with the same role anyone else has by default.
        </p>
      </div>

      <div className="rounded-2xl border border-border bg-surface p-4 space-y-3">
        <div className="text-[11px] font-mono uppercase tracking-wider text-muted">
          Invite link
        </div>
        {error ? (
          <div className="text-[12px] text-error">{error}</div>
        ) : inviteUrl ? (
          <div className="flex items-center gap-2">
            <code className="flex-1 truncate rounded-md border border-border-subtle bg-background/40 px-3 py-2 text-[12px] font-mono text-foreground">
              {inviteUrl}
            </code>
            <button
              type="button"
              onClick={handleCopy}
              className="rounded-md bg-brand px-3 py-2 text-[12px] font-medium text-white hover:bg-brand-hover transition-colors"
            >
              {copied ? "Copied" : "Copy"}
            </button>
          </div>
        ) : (
          <div className="text-[12px] text-muted">Loading…</div>
        )}
        <div className="text-[11px] text-muted">
          You can rotate this link anytime from workspace settings.
        </div>
      </div>
    </div>
  );
}
