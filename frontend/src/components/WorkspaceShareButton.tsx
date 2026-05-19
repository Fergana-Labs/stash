"use client";

import { FormEvent, useCallback, useEffect, useRef, useState } from "react";
import {
  apiFetch,
  createInviteToken,
  getMe,
  getWorkspaceMembers,
} from "../lib/api";
import type { WorkspaceMember } from "../lib/types";
import { useEscapeKey } from "../hooks/useEscapeKey";

interface WorkspaceShareButtonProps {
  workspaceId: string;
  workspaceName?: string;
}

const PALETTE = [
  { bg: "bg-rose-200", fg: "text-rose-800" },
  { bg: "bg-indigo-200", fg: "text-indigo-800" },
  { bg: "bg-emerald-200", fg: "text-emerald-800" },
  { bg: "bg-amber-200", fg: "text-amber-900" },
  { bg: "bg-sky-200", fg: "text-sky-800" },
  { bg: "bg-fuchsia-200", fg: "text-fuchsia-800" },
];

export default function WorkspaceShareButton({
  workspaceId,
  workspaceName = "Workspace",
}: WorkspaceShareButtonProps) {
  const [open, setOpen] = useState(false);
  const [members, setMembers] = useState<WorkspaceMember[]>([]);
  const [meId, setMeId] = useState<string | null>(null);
  const [username, setUsername] = useState("");
  const [inviteLink, setInviteLink] = useState("");
  const [msg, setMsg] = useState("");
  const [busy, setBusy] = useState(false);
  const [copied, setCopied] = useState(false);
  const [loading, setLoading] = useState(false);
  const popoverRef = useRef<HTMLDivElement>(null);

  useEscapeKey(open, () => setOpen(false));

  const loadMembers = useCallback(async () => {
    setLoading(true);
    try {
      const [nextMembers, me] = await Promise.all([
        getWorkspaceMembers(workspaceId),
        getMe(),
      ]);
      setMembers(nextMembers);
      setMeId(me.id);
    } catch (e) {
      setMsg(e instanceof Error ? e.message : "Failed to load members.");
    } finally {
      setLoading(false);
    }
  }, [workspaceId]);

  useEffect(() => {
    if (!open) return;

    function onDown(e: globalThis.MouseEvent) {
      if (!popoverRef.current) return;
      if (!popoverRef.current.contains(e.target as Node)) setOpen(false);
    }

    document.addEventListener("mousedown", onDown);
    return () => document.removeEventListener("mousedown", onDown);
  }, [open]);

  useEffect(() => {
    if (!open) return;

    setMsg("");
    setInviteLink("");
    setUsername("");
    setCopied(false);
    void loadMembers();
  }, [open, loadMembers]);

  const myRole = members.find((m) => m.user_id === meId)?.role;
  const canInvite = myRole === "owner";

  async function addByUsername(e: FormEvent) {
    e.preventDefault();
    const nextUsername = username.trim();
    if (!nextUsername) return;

    setBusy(true);
    setMsg("");
    try {
      await apiFetch(`/api/v1/workspaces/${workspaceId}/members`, {
        method: "POST",
        body: JSON.stringify({ username: nextUsername }),
      });
      setUsername("");
      setMsg("Added.");
      await loadMembers();
    } catch (e) {
      setMsg(e instanceof Error ? e.message : "Failed to add member.");
    } finally {
      setBusy(false);
    }
  }

  async function generateLink() {
    setBusy(true);
    setMsg("");
    try {
      const res = await createInviteToken(workspaceId, 5, 7);
      setInviteLink(absoluteUrl(`/join/${res.token}`));
      setCopied(false);
    } catch (e) {
      setMsg(e instanceof Error ? e.message : "Failed to create invite link.");
    } finally {
      setBusy(false);
    }
  }

  async function copyInviteLink() {
    if (!inviteLink) return;

    try {
      await navigator.clipboard.writeText(inviteLink);
      setCopied(true);
      setMsg("Link copied.");
      window.setTimeout(() => setCopied(false), 1600);
    } catch {
      setMsg("Failed to copy link.");
    }
  }

  return (
    <div ref={popoverRef} className="relative">
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        aria-haspopup="dialog"
        aria-expanded={open}
        className="rounded-md bg-[var(--color-brand-600)] px-2.5 py-1 text-[12.5px] font-medium text-white hover:bg-[var(--color-brand-700)]"
      >
        Share
      </button>
      {open && (
        <div
          role="dialog"
          aria-label={`Share ${workspaceName}`}
          className="absolute right-0 top-full z-40 mt-1.5 w-[320px] rounded-lg border border-border bg-base p-3 shadow-lg"
        >
          <div className="sys-label mb-1">Invite link</div>
          {inviteLink ? (
            <div className="flex gap-1.5">
              <input
                readOnly
                value={inviteLink}
                className="min-w-0 flex-1 rounded-md border border-border bg-surface px-2 py-1.5 text-[11.5px] font-mono text-foreground"
              />
              <button
                type="button"
                onClick={() => void copyInviteLink()}
                className="rounded-md border border-border bg-base px-2 py-1.5 text-[11.5px] font-medium text-foreground hover:bg-raised"
              >
                {copied ? "Copied" : "Copy"}
              </button>
            </div>
          ) : (
            <button
              type="button"
              onClick={() => void generateLink()}
              disabled={busy || loading || !canInvite}
              className="w-full rounded-md border border-border bg-base px-2 py-1.5 text-left text-[12px] font-medium text-foreground hover:bg-raised disabled:opacity-40"
            >
              Generate invite link
            </button>
          )}

          <div className="sys-label mb-1 mt-3">Invite by username</div>
          {canInvite ? (
            <form onSubmit={addByUsername} className="flex gap-1.5">
              <input
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                placeholder="Username"
                className="min-w-0 flex-1 rounded-md border border-border bg-surface px-2 py-1.5 text-[12px] text-foreground placeholder:text-muted focus:border-[var(--color-brand-400)] focus:outline-none"
              />
              <button
                type="submit"
                disabled={busy || !username.trim()}
                className="rounded-md border border-border bg-base px-2 py-1.5 text-[11.5px] font-medium text-foreground hover:bg-raised disabled:opacity-40"
              >
                Add
              </button>
            </form>
          ) : (
            <div className="rounded-md border border-border bg-surface px-2 py-1.5 text-[12px] text-muted">
              {loading
                ? "Loading members..."
                : "Only workspace admins can invite new people."}
            </div>
          )}

          <div className="sys-label mb-1 mt-3">Members</div>
          <ul className="max-h-44 overflow-y-auto">
            {members.map((member) => (
              <MemberRow
                key={member.user_id}
                member={member}
                isMe={member.user_id === meId}
              />
            ))}
            {members.length === 0 && (
              <li className="py-2 text-[12px] text-muted">
                {loading ? "Loading..." : "No members found."}
              </li>
            )}
          </ul>

          {msg && <div className="mt-2 text-[12px] text-muted">{msg}</div>}
        </div>
      )}
    </div>
  );
}

function MemberRow({
  member,
  isMe,
}: {
  member: WorkspaceMember;
  isMe: boolean;
}) {
  const label = member.display_name || member.name;
  const color = colorFor(label);

  return (
    <li className="flex items-center gap-2.5 py-1 text-[13px]">
      <span
        className={
          "inline-flex h-6 w-6 flex-shrink-0 items-center justify-center rounded-full text-[9px] font-semibold " +
          color.bg +
          " " +
          color.fg
        }
      >
        {label.slice(0, 2).toUpperCase()}
      </span>
      <span className="min-w-0 flex-1 truncate font-medium text-foreground">
        {label}
        {isMe ? <span className="ml-1 text-[10px] text-muted">(you)</span> : null}
      </span>
      <span className="rounded bg-surface px-1.5 py-0.5 text-[10px] uppercase tracking-wide text-muted ring-1 ring-border">
        {roleLabel(member.role)}
      </span>
    </li>
  );
}

function colorFor(name: string) {
  let h = 5381;
  for (let i = 0; i < name.length; i++) h = (h * 33 + name.charCodeAt(i)) >>> 0;
  return PALETTE[h % PALETTE.length];
}

function roleLabel(role: string): string {
  if (role === "owner") return "admin";
  return role;
}

function absoluteUrl(path: string): string {
  if (typeof window === "undefined") return path;
  return `${window.location.origin}${path}`;
}
