"use client";

import { useEffect, useState } from "react";
import {
  apiFetch,
  createInviteToken,
  getMe,
  getWorkspaceMembers,
  kickWorkspaceMember,
  setWorkspaceMemberRole,
} from "../lib/api";
import type { WorkspaceMember } from "../lib/types";

interface MembersModalProps {
  stashId: string;
  open: boolean;
  onClose: () => void;
}

const PALETTE = [
  { bg: "bg-rose-200", fg: "text-rose-800" },
  { bg: "bg-indigo-200", fg: "text-indigo-800" },
  { bg: "bg-emerald-200", fg: "text-emerald-800" },
  { bg: "bg-amber-200", fg: "text-amber-900" },
  { bg: "bg-sky-200", fg: "text-sky-800" },
  { bg: "bg-fuchsia-200", fg: "text-fuchsia-800" },
];
function colorFor(name: string) {
  let h = 5381;
  for (let i = 0; i < name.length; i++) h = (h * 33 + name.charCodeAt(i)) >>> 0;
  return PALETTE[h % PALETTE.length];
}

export default function MembersModal({ stashId, open, onClose }: MembersModalProps) {
  const [members, setMembers] = useState<WorkspaceMember[]>([]);
  const [meId, setMeId] = useState<string | null>(null);
  const [username, setUsername] = useState("");
  const [inviteLink, setInviteLink] = useState("");
  const [msg, setMsg] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (!open) return;
    setMsg("");
    setInviteLink("");
    setUsername("");
    getWorkspaceMembers(stashId).then(setMembers).catch(() => {});
    getMe().then((u) => setMeId(u.id)).catch(() => {});
  }, [open, stashId]);

  if (!open) return null;

  const myRole = members.find((m) => m.user_id === meId)?.role;
  const canAdmin = myRole === "owner";

  async function changeRole(userId: string, role: "owner" | "editor" | "viewer") {
    try {
      await setWorkspaceMemberRole(stashId, userId, role);
      setMembers(await getWorkspaceMembers(stashId));
      setMsg("Role updated.");
    } catch (e) {
      setMsg((e as Error).message || "Failed");
    }
  }

  async function kick(userId: string) {
    if (!confirm("Remove this member from the stash?")) return;
    try {
      await kickWorkspaceMember(stashId, userId);
      setMembers(await getWorkspaceMembers(stashId));
    } catch (e) {
      setMsg((e as Error).message || "Failed");
    }
  }

  async function addByUsername(e: React.FormEvent) {
    e.preventDefault();
    if (!username.trim()) return;
    setBusy(true);
    setMsg("");
    try {
      await apiFetch(`/api/v1/workspaces/${stashId}/members`, {
        method: "POST",
        body: JSON.stringify({ username: username.trim() }),
      });
      setUsername("");
      setMsg("Added.");
      setMembers(await getWorkspaceMembers(stashId));
    } catch (err) {
      setMsg((err as Error).message || "Failed");
    }
    setBusy(false);
  }

  async function generateLink() {
    setBusy(true);
    try {
      const res = await createInviteToken(stashId, 5, 7);
      setInviteLink(
        `${window.location.origin}/join/${res.token}`
      );
    } catch (err) {
      setMsg((err as Error).message || "Failed");
    }
    setBusy(false);
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 px-4" onClick={onClose}>
      <div className="w-full max-w-md rounded-2xl border border-border bg-base shadow-xl" onClick={(e) => e.stopPropagation()}>
        <div className="flex items-center justify-between border-b border-border px-5 py-3">
          <h2 className="font-display text-[15px] font-semibold text-foreground">Members</h2>
          <button onClick={onClose} className="text-muted hover:text-foreground">✕</button>
        </div>

        <div className="px-5 py-4">
          <ul className="flex flex-col gap-2">
            {members.map((m) => {
              const label = m.display_name || m.name;
              const c = colorFor(label);
              const isMe = m.user_id === meId;
              return (
                <li key={m.user_id} className="flex items-center gap-2.5 text-[13px]">
                  <span className={"inline-flex h-6 w-6 items-center justify-center rounded-full text-[9px] font-semibold " + c.bg + " " + c.fg}>
                    {label.slice(0, 2).toUpperCase()}
                  </span>
                  <span className="flex-1 truncate font-medium text-foreground">
                    {label}
                    {isMe ? <span className="ml-1 text-[10px] text-muted">(you)</span> : null}
                  </span>
                  {canAdmin && !isMe ? (
                    <select
                      value={m.role}
                      onChange={(e) => changeRole(m.user_id, e.target.value as "owner" | "editor" | "viewer")}
                      className="rounded border border-border bg-surface px-1.5 py-0.5 text-[10px] uppercase tracking-wide text-foreground"
                    >
                      <option value="owner">Owner</option>
                      <option value="editor">Editor</option>
                      <option value="viewer">Viewer</option>
                    </select>
                  ) : (
                    <span className="rounded bg-surface px-1.5 py-0.5 text-[10px] uppercase tracking-wide text-muted ring-1 ring-border">
                      {m.role}
                    </span>
                  )}
                  {canAdmin && !isMe && m.role !== "owner" && (
                    <button
                      onClick={() => kick(m.user_id)}
                      title="Remove from stash"
                      className="text-[12px] text-muted hover:text-red-400"
                    >
                      ✕
                    </button>
                  )}
                </li>
              );
            })}
          </ul>

          <form onSubmit={addByUsername} className="mt-4 flex gap-2">
            <input
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              placeholder="Invite by username"
              className="flex-1 rounded-md border border-border bg-surface px-2.5 py-1.5 text-[12.5px] text-foreground placeholder:text-muted focus:border-[var(--color-brand-400)] focus:outline-none"
            />
            <button
              type="submit"
              disabled={busy || !username.trim()}
              className="rounded-md bg-[var(--color-brand-600)] px-3 py-1.5 text-[12px] font-medium text-white hover:bg-[var(--color-brand-700)] disabled:opacity-40"
            >
              Add
            </button>
          </form>

          <div className="mt-3 flex items-center gap-2">
            <button
              onClick={generateLink}
              disabled={busy}
              className="rounded-md border border-border bg-base px-3 py-1.5 text-[12px] text-foreground hover:bg-raised disabled:opacity-40"
            >
              Generate invite link
            </button>
            {inviteLink && (
              <button
                onClick={async () => {
                  await navigator.clipboard.writeText(inviteLink);
                  setMsg("Link copied.");
                }}
                className="truncate text-[11px] font-mono text-[var(--color-brand-700)] hover:underline"
              >
                {inviteLink}
              </button>
            )}
          </div>

          {msg && <div className="mt-2 text-[12px] text-muted">{msg}</div>}
        </div>
      </div>
    </div>
  );
}
