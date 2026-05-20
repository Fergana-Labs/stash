"use client";

import { useEffect, useState } from "react";

import { apiFetch, getWorkspace, publishStash } from "@/lib/api";
import type { StepCtx } from "@/lib/onboarding/paths";

type Page = { id: string; name: string; content_type: string };
type FileRow = { id: string; name: string };
type Overview = {
  files: {
    pages: Page[];
    files: FileRow[];
  };
};

type ItemKind = "page" | "file";

type SharedItem = {
  kind: ItemKind;
  id: string;
  name: string;
  contentType?: string;
};

const APP_URL = typeof window !== "undefined" ? window.location.origin : "";

export default function SharingBrowseStep({ workspaceId }: StepCtx) {
  const [overview, setOverview] = useState<Overview | null>(null);
  const [inviteCode, setInviteCode] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!workspaceId) return;
    apiFetch<Overview>(`/api/v1/workspaces/${workspaceId}/overview`)
      .then(setOverview)
      .catch((e) => setError(e instanceof Error ? e.message : String(e)));
    getWorkspace(workspaceId)
      .then((ws) => setInviteCode(ws.invite_code))
      .catch(() => {});
  }, [workspaceId]);

  const items: SharedItem[] = [
    ...(overview?.files.pages ?? []).map<SharedItem>((p) => ({
      kind: "page",
      id: p.id,
      name: p.name,
      contentType: p.content_type,
    })),
    ...(overview?.files.files ?? []).map<SharedItem>((f) => ({
      kind: "file",
      id: f.id,
      name: f.name,
    })),
  ];

  const inviteUrl =
    inviteCode && APP_URL ? `${APP_URL}/join/${inviteCode}` : null;

  return (
    <div className="space-y-6">
      <div>
        <h1 className="font-display text-[28px] leading-[1.1] font-bold tracking-tight text-foreground">
          {items.length > 0 ? "Here's what you just added" : "Nothing here yet"}
        </h1>
      </div>

      {error && (
        <div className="text-[12px] text-error rounded-lg border border-error/30 bg-error/10 px-3 py-2">
          {error}
        </div>
      )}

      {items.length === 0 ? (
        <p className="text-sm text-dim max-w-md">
          Go back and drop a file, or have your agent publish one — then come
          back.
        </p>
      ) : (
        <div className="rounded-2xl border border-border bg-surface divide-y divide-border-subtle">
          {items.map((item) => (
            <ItemRow
              key={`${item.kind}-${item.id}`}
              item={item}
              workspaceId={workspaceId!}
              inviteUrl={inviteUrl}
            />
          ))}
        </div>
      )}
    </div>
  );
}

function ItemRow({
  item,
  workspaceId,
  inviteUrl,
}: {
  item: SharedItem;
  workspaceId: string;
  inviteUrl: string | null;
}) {
  const [open, setOpen] = useState(false);
  const [publicUrl, setPublicUrl] = useState<string | null>(null);
  const [creating, setCreating] = useState(false);
  const [shareError, setShareError] = useState<string | null>(null);

  async function createPublicLink() {
    if (publicUrl || creating) return;
    setCreating(true);
    setShareError(null);
    try {
      const result = await publishStash(
        workspaceId,
        item.name,
        [{ object_type: item.kind, object_id: item.id }],
        { public_permission: "read" },
      );
      setPublicUrl(result.url);
    } catch (e) {
      setShareError(e instanceof Error ? e.message : String(e));
    } finally {
      setCreating(false);
    }
  }

  const icon = item.kind === "file" ? "📎" : item.contentType === "html" ? "🌐" : "📄";
  const tag = item.kind === "file" ? "file" : item.contentType ?? "page";

  return (
    <div>
      <div className="flex items-center justify-between gap-3 px-4 py-3">
        <a
          href={item.kind === "file" ? `/files/${item.id}` : `/pages/${item.id}`}
          className="flex items-center gap-3 min-w-0 hover:underline"
        >
          <span className="text-[14px]" aria-hidden>
            {icon}
          </span>
          <span className="text-[13px] text-foreground truncate">{item.name}</span>
        </a>
        <div className="flex items-center gap-3 shrink-0">
          <span className="text-[10px] font-mono uppercase tracking-wider text-muted">
            {tag}
          </span>
          <button
            type="button"
            onClick={() => setOpen((v) => !v)}
            className="rounded-md border border-border-subtle bg-background/40 px-2.5 py-1 text-[11.5px] font-medium text-foreground hover:bg-raised"
          >
            {open ? "Close" : "Share"}
          </button>
        </div>
      </div>

      {open && (
        <div className="px-4 pb-4 -mt-1 space-y-3 bg-background/40">
          <SharePanel
            publicUrl={publicUrl}
            creating={creating}
            shareError={shareError}
            inviteUrl={inviteUrl}
            onCreatePublicLink={createPublicLink}
          />
        </div>
      )}
    </div>
  );
}

function SharePanel({
  publicUrl,
  creating,
  shareError,
  inviteUrl,
  onCreatePublicLink,
}: {
  publicUrl: string | null;
  creating: boolean;
  shareError: string | null;
  inviteUrl: string | null;
  onCreatePublicLink: () => void;
}) {
  return (
    <div className="grid grid-cols-1 md:grid-cols-2 gap-3 pt-3">
      <section className="rounded-xl border border-border-subtle bg-surface p-3 space-y-2">
        <div className="text-[11px] font-mono uppercase tracking-wider text-muted">
          Public link
        </div>
        <p className="text-[11.5px] text-muted leading-relaxed">
          Anyone with this link can view this item. No account needed.
        </p>
        {publicUrl ? (
          <CopyableUrl url={publicUrl} />
        ) : (
          <button
            type="button"
            onClick={onCreatePublicLink}
            disabled={creating}
            className="rounded-md bg-brand px-3 py-1.5 text-[12px] font-medium text-white hover:bg-brand-hover disabled:opacity-60"
          >
            {creating ? "Creating…" : "Get a public link"}
          </button>
        )}
        {shareError && <p className="text-[11px] text-error">{shareError}</p>}
      </section>

      <section className="rounded-xl border border-border-subtle bg-surface p-3 space-y-2">
        <div className="text-[11px] font-mono uppercase tracking-wider text-muted">
          Invite to workspace
        </div>
        <p className="text-[11.5px] text-muted leading-relaxed">
          Anyone who joins via this link can see — and collaborate on —
          everything in your workspace.
        </p>
        {inviteUrl ? (
          <CopyableUrl url={inviteUrl} />
        ) : (
          <p className="text-[11.5px] text-muted">Loading invite link…</p>
        )}
      </section>
    </div>
  );
}

function CopyableUrl({ url }: { url: string }) {
  const [copied, setCopied] = useState(false);

  async function handleCopy() {
    await navigator.clipboard.writeText(url);
    setCopied(true);
    setTimeout(() => setCopied(false), 1500);
  }

  return (
    <div className="flex items-center gap-1.5">
      <code className="flex-1 truncate rounded-md border border-border-subtle bg-background/40 px-2 py-1.5 text-[11px] font-mono text-foreground">
        {url}
      </code>
      <button
        type="button"
        onClick={handleCopy}
        className="rounded-md bg-brand px-2.5 py-1.5 text-[11px] font-medium text-white hover:bg-brand-hover"
      >
        {copied ? "Copied" : "Copy"}
      </button>
    </div>
  );
}
