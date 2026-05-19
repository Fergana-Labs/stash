"use client";

import { FormEvent, useState } from "react";
import {
  apiFetch,
  createInviteToken,
  kickWorkspaceMember,
  setWorkspaceMemberRole,
} from "../../lib/api";
import type { WorkspaceMember } from "../../lib/types";
import CustomSelect from "../CustomSelect";

interface WorkspaceMembersPanelProps {
  workspaceId: string;
  members: WorkspaceMember[];
  currentUserId: string;
  canManage: boolean;
  onReload: () => Promise<void>;
  showInviteControls?: boolean;
}

const MEMBER_ROLE_OPTIONS = [
  { value: "viewer", label: "Viewer" },
  { value: "editor", label: "Editor" },
  { value: "owner", label: "Admin" },
];

const PALETTE = [
  { bg: "bg-rose-200", fg: "text-rose-800" },
  { bg: "bg-indigo-200", fg: "text-indigo-800" },
  { bg: "bg-emerald-200", fg: "text-emerald-800" },
  { bg: "bg-amber-200", fg: "text-amber-900" },
  { bg: "bg-sky-200", fg: "text-sky-800" },
  { bg: "bg-fuchsia-200", fg: "text-fuchsia-800" },
];

export default function WorkspaceMembersPanel({
  workspaceId,
  members,
  currentUserId,
  canManage,
  onReload,
  showInviteControls = true,
}: WorkspaceMembersPanelProps) {
  const [username, setUsername] = useState("");
  const [inviteLink, setInviteLink] = useState("");
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);

  async function addByUsername(event: FormEvent) {
    event.preventDefault();
    const nextUsername = username.trim();
    if (!nextUsername) return;

    setBusy(true);
    setMessage("");
    try {
      await apiFetch(`/api/v1/workspaces/${workspaceId}/members`, {
        method: "POST",
        body: JSON.stringify({ username: nextUsername }),
      });
      setUsername("");
      setMessage("Added.");
      await onReload();
    } catch (e) {
      setMessage(e instanceof Error ? e.message : "Failed to add member.");
    } finally {
      setBusy(false);
    }
  }

  async function generateInviteLink() {
    setBusy(true);
    setMessage("");
    try {
      const result = await createInviteToken(workspaceId, 5, 7);
      setInviteLink(`${window.location.origin}/join/${result.token}`);
    } catch (e) {
      setMessage(e instanceof Error ? e.message : "Failed to create invite link.");
    } finally {
      setBusy(false);
    }
  }

  async function copyInviteLink() {
    if (!inviteLink) return;
    try {
      await navigator.clipboard.writeText(inviteLink);
      setMessage("Link copied.");
    } catch {
      setMessage("Failed to copy link.");
    }
  }

  async function changeRole(userId: string, role: "owner" | "editor" | "viewer") {
    try {
      await setWorkspaceMemberRole(workspaceId, userId, role);
      setMessage("Role updated.");
      await onReload();
    } catch (e) {
      setMessage(e instanceof Error ? e.message : "Failed to update role.");
    }
  }

  async function removeMember(userId: string) {
    if (!confirm("Remove this member from the workspace?")) return;
    try {
      await kickWorkspaceMember(workspaceId, userId);
      setMessage("Removed.");
      await onReload();
    } catch (e) {
      setMessage(e instanceof Error ? e.message : "Failed to remove member.");
    }
  }

  return (
    <div className="space-y-5">
      {showInviteControls && (
        <div className="rounded-lg border border-border bg-base p-4">
          <div className="text-[13.5px] font-medium text-foreground">Invite members</div>
          <div className="mt-3 grid gap-3 sm:grid-cols-[minmax(0,1fr)_auto]">
            <form onSubmit={addByUsername} className="flex min-w-0 gap-2">
              <input
                value={username}
                onChange={(event) => setUsername(event.target.value)}
                placeholder="Username"
                disabled={!canManage || busy}
                className="min-w-0 flex-1 rounded-md border border-border bg-surface px-2.5 py-1.5 text-[12.5px] text-foreground placeholder:text-muted focus:border-[var(--color-brand-400)] focus:outline-none disabled:opacity-50"
              />
              <button
                type="submit"
                disabled={!canManage || busy || !username.trim()}
                className="rounded-md bg-[var(--color-brand-600)] px-3 py-1.5 text-[12px] font-medium text-white hover:bg-[var(--color-brand-700)] disabled:opacity-40"
              >
                Add
              </button>
            </form>
            <button
              type="button"
              onClick={() => void generateInviteLink()}
              disabled={!canManage || busy}
              className="rounded-md border border-border bg-base px-3 py-1.5 text-[12px] font-medium text-foreground hover:bg-raised disabled:opacity-40"
            >
              Generate invite link
            </button>
          </div>
          {inviteLink && (
            <button
              type="button"
              onClick={() => void copyInviteLink()}
              className="mt-3 max-w-full truncate rounded-md border border-border bg-surface px-2.5 py-1.5 text-left font-mono text-[11.5px] text-[var(--color-brand-700)] hover:bg-raised"
            >
              {inviteLink}
            </button>
          )}
          {!canManage && (
            <div className="mt-2 text-[12px] text-muted">
              Only workspace admins can invite new people.
            </div>
          )}
        </div>
      )}

      <ul className="flex flex-col gap-2">
        {members.map((member) => (
          <MemberRow
            key={member.user_id}
            member={member}
            isMe={member.user_id === currentUserId}
            canManage={canManage}
            onRoleChange={changeRole}
            onRemove={removeMember}
          />
        ))}
        {members.length === 0 && (
          <li className="rounded-lg border border-border bg-base px-3 py-5 text-center text-[12.5px] text-muted">
            No members found.
          </li>
        )}
      </ul>

      {message && <div className="text-[12px] text-muted">{message}</div>}
    </div>
  );
}

function MemberRow({
  member,
  isMe,
  canManage,
  onRoleChange,
  onRemove,
}: {
  member: WorkspaceMember;
  isMe: boolean;
  canManage: boolean;
  onRoleChange: (userId: string, role: "owner" | "editor" | "viewer") => Promise<void>;
  onRemove: (userId: string) => Promise<void>;
}) {
  const label = member.display_name || member.name;
  const color = colorFor(label);
  const canEditMember = canManage && !isMe;

  return (
    <li className="flex items-center gap-3 rounded-lg border border-border bg-base px-3 py-2">
      <span
        className={
          "inline-flex h-8 w-8 flex-shrink-0 items-center justify-center rounded-full text-[10px] font-semibold " +
          color.bg +
          " " +
          color.fg
        }
      >
        {label.slice(0, 2).toUpperCase()}
      </span>
      <div className="min-w-0 flex-1">
        <div className="truncate text-[13.5px] font-medium text-foreground">
          {label}
          {isMe ? <span className="ml-1 text-[10px] text-muted">(you)</span> : null}
        </div>
        <div className="truncate text-[11.5px] text-muted">@{member.name}</div>
      </div>
      <div className="flex items-center gap-2">
        {canEditMember ? (
          <CustomSelect
            value={member.role}
            options={MEMBER_ROLE_OPTIONS}
            onChange={(next) =>
              void onRoleChange(member.user_id, next as "owner" | "editor" | "viewer")
            }
            className="min-w-[82px] rounded border border-border bg-surface px-2 py-1 text-[12px]"
            align="right"
          />
        ) : (
          <span className="rounded bg-raised px-2 py-0.5 text-[11.5px] text-muted">
            {roleLabel(member.role)}
          </span>
        )}
        {canEditMember && member.role !== "owner" && (
          <button
            type="button"
            onClick={() => void onRemove(member.user_id)}
            className="text-[11.5px] text-red-500 hover:underline"
          >
            Remove
          </button>
        )}
      </div>
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
