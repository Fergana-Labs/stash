"use client";

import { FormEvent, useCallback, useEffect, useRef, useState } from "react";
import { useEscapeKey } from "../../hooks/useEscapeKey";
import {
  addStashMember,
  ApiError,
  getMe,
  listStashMembers,
  removeStashMember,
  searchUsers,
  updateStash,
  type PublicStashDetail,
  type StashMember,
  type StashMemberPermission,
} from "../../lib/api";
import { resetStashNavigationCache } from "../../lib/stashNavigationCache";
import type { UserSearchResult } from "../../lib/types";

type StashAccess = PublicStashDetail["stash"]["access"];

const PERMISSION_OPTIONS: { value: StashMemberPermission; label: string }[] = [
  { value: "read", label: "Read" },
  { value: "write", label: "Write" },
  { value: "admin", label: "Admin" },
];

const PALETTE = [
  { bg: "bg-rose-200", fg: "text-rose-800" },
  { bg: "bg-indigo-200", fg: "text-indigo-800" },
  { bg: "bg-emerald-200", fg: "text-emerald-800" },
  { bg: "bg-amber-200", fg: "text-amber-900" },
  { bg: "bg-sky-200", fg: "text-sky-800" },
  { bg: "bg-fuchsia-200", fg: "text-fuchsia-800" },
];

export default function StashShareButton({
  stash,
  canWrite,
  onChanged,
}: {
  stash: PublicStashDetail["stash"];
  canWrite: boolean;
  onChanged: () => Promise<void>;
}) {
  const [open, setOpen] = useState(false);
  const [copied, setCopied] = useState(false);
  const [vis, setVis] = useState<StashAccess>(stash.access);
  const [discoverable, setDiscoverable] = useState(stash.discoverable);
  const [saving, setSaving] = useState(false);
  const [shareMessage, setShareMessage] = useState("");
  const [members, setMembers] = useState<StashMember[]>([]);
  const [meId, setMeId] = useState<string | null>(null);
  const [membersLoading, setMembersLoading] = useState(false);
  const [canManageMembers, setCanManageMembers] = useState(false);
  const [memberBusy, setMemberBusy] = useState(false);
  const [memberMessage, setMemberMessage] = useState("");
  const [userQuery, setUserQuery] = useState("");
  const [userResults, setUserResults] = useState<UserSearchResult[]>([]);
  const [newMemberPermission, setNewMemberPermission] =
    useState<StashMemberPermission>("read");
  const popoverRef = useRef<HTMLDivElement>(null);

  useEscapeKey(open, () => setOpen(false));

  useEffect(() => {
    setVis(stash.access);
    setDiscoverable(stash.discoverable);
  }, [stash.access, stash.discoverable]);

  const loadMembers = useCallback(async () => {
    setMembersLoading(true);
    setMemberMessage("");
    try {
      const [nextMembers, me] = await Promise.all([
        listStashMembers(stash.id),
        getMe(),
      ]);
      setMembers(nextMembers);
      setMeId(me.id);
      setCanManageMembers(true);
    } catch (e) {
      if (e instanceof ApiError && e.status === 403) {
        setMembers([]);
        setCanManageMembers(false);
        return;
      }
      setMemberMessage(e instanceof Error ? e.message : "Failed to load members.");
    } finally {
      setMembersLoading(false);
    }
  }, [stash.id]);

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
    if (!open || !canWrite) return;

    setShareMessage("");
    setMemberMessage("");
    setUserQuery("");
    setUserResults([]);
    setCopied(false);
    void loadMembers();
  }, [open, canWrite, loadMembers]);

  async function copyLink() {
    try {
      await navigator.clipboard.writeText(absoluteUrl(`/stashes/${stash.slug}`));
      setCopied(true);
      setShareMessage("Link copied.");
      window.setTimeout(() => setCopied(false), 1600);
    } catch {
      setShareMessage("Failed to copy link.");
    }
  }

  async function applyVisibility(nextAccess: StashAccess) {
    const nextDiscoverable = nextAccess === "public" ? discoverable : false;

    setSaving(true);
    setShareMessage("");
    try {
      const updated = await updateStash(stash.id, {
        access: nextAccess,
        discoverable: nextDiscoverable,
      });
      setVis(updated.access);
      setDiscoverable(updated.discoverable);
      resetStashNavigationCache();
      await onChanged();
    } catch (e) {
      setShareMessage(e instanceof Error ? e.message : "Could not update visibility.");
    } finally {
      setSaving(false);
    }
  }

  async function toggleDiscoverable(nextDiscoverable: boolean) {
    setSaving(true);
    setShareMessage("");
    try {
      const updated = await updateStash(stash.id, {
        access: "public",
        discoverable: nextDiscoverable,
      });
      setVis(updated.access);
      setDiscoverable(updated.discoverable);
      resetStashNavigationCache();
      await onChanged();
    } catch (e) {
      setShareMessage(e instanceof Error ? e.message : "Could not update Discover.");
    } finally {
      setSaving(false);
    }
  }

  async function searchForUsers(e: FormEvent) {
    e.preventDefault();
    const query = userQuery.trim();
    if (!query) return;

    setMemberBusy(true);
    setMemberMessage("");
    try {
      setUserResults(await searchUsers(query));
    } catch (e) {
      setMemberMessage(e instanceof Error ? e.message : "Could not search users.");
    } finally {
      setMemberBusy(false);
    }
  }

  async function addMember(userId: string) {
    setMemberBusy(true);
    setMemberMessage("");
    try {
      await addStashMember(stash.id, userId, newMemberPermission);
      await loadMembers();
      setUserQuery("");
      setUserResults([]);
      setMemberMessage("Added.");
      resetStashNavigationCache();
    } catch (e) {
      setMemberMessage(e instanceof Error ? e.message : "Could not add member.");
    } finally {
      setMemberBusy(false);
    }
  }

  async function changeMemberPermission(
    userId: string,
    permission: StashMemberPermission,
  ) {
    setMemberBusy(true);
    setMemberMessage("");
    try {
      await addStashMember(stash.id, userId, permission);
      await loadMembers();
      setMemberMessage("Updated.");
      resetStashNavigationCache();
    } catch (e) {
      setMemberMessage(e instanceof Error ? e.message : "Could not update member.");
    } finally {
      setMemberBusy(false);
    }
  }

  async function deleteMember(userId: string) {
    if (!confirm("Remove this member from the Stash?")) return;

    setMemberBusy(true);
    setMemberMessage("");
    try {
      await removeStashMember(stash.id, userId);
      await loadMembers();
      resetStashNavigationCache();
    } catch (e) {
      setMemberMessage(e instanceof Error ? e.message : "Could not remove member.");
    } finally {
      setMemberBusy(false);
    }
  }

  const ownerLabel = stash.owner_display_name || stash.owner_name;

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
          aria-label={`Share ${stash.title}`}
          className="absolute right-0 top-full z-40 mt-1.5 w-[360px] rounded-lg border border-border bg-base p-3 shadow-lg"
        >
          <div className="sys-label mb-1">Public URL</div>
          <div className="flex gap-1.5">
            <input
              readOnly
              value={absoluteUrl(`/stashes/${stash.slug}`)}
              className="min-w-0 flex-1 rounded-md border border-border bg-surface px-2 py-1.5 text-[11.5px] font-mono text-foreground"
            />
            <button
              type="button"
              onClick={() => void copyLink()}
              className="rounded-md border border-border bg-base px-2 py-1.5 text-[11.5px] font-medium text-foreground hover:bg-raised"
            >
              {copied ? "Copied" : "Copy"}
            </button>
          </div>

          {canWrite && (
            <>
              <div className="sys-label mb-1 mt-3">Visibility</div>
              <div className="flex flex-col gap-1">
                <VisOption
                  label="Workspace"
                  hint="Anyone in the owning workspace can view"
                  value="workspace"
                  current={vis}
                  onChange={(v) => void applyVisibility(v)}
                />
                <VisOption
                  label="Private"
                  hint="Only the owner and explicit members"
                  value="private"
                  current={vis}
                  onChange={(v) => void applyVisibility(v)}
                />
                <VisOption
                  label="Public"
                  hint="Anyone with the URL can view"
                  value="public"
                  current={vis}
                  onChange={(v) => void applyVisibility(v)}
                />
              </div>

              {vis === "public" && (
                <label className="mt-3 flex cursor-pointer items-center gap-2 rounded-md border border-border bg-surface px-2 py-1.5">
                  <input
                    type="checkbox"
                    checked={discoverable}
                    onChange={(e) => void toggleDiscoverable(e.target.checked)}
                  />
                  <span className="text-[12px] text-foreground">
                    List on Discover
                  </span>
                </label>
              )}

              <div className="mt-4 border-t border-border pt-3">
                <div className="sys-label mb-2">Members</div>
                <OwnerRow label={ownerLabel} username={stash.owner_name} />

                {membersLoading && (
                  <div className="mt-2 rounded-md border border-border bg-surface px-2 py-1.5 text-[12px] text-muted">
                    Loading members...
                  </div>
                )}

                {!membersLoading && canManageMembers && (
                  <>
                    <ul className="mt-2 max-h-44 overflow-y-auto pr-1">
                      {members.map((member) => (
                        <MemberRow
                          key={member.user_id}
                          member={member}
                          isMe={member.user_id === meId}
                          busy={memberBusy}
                          onPermissionChange={(permission) =>
                            void changeMemberPermission(member.user_id, permission)
                          }
                          onRemove={
                            meId && member.user_id !== meId
                              ? () => void deleteMember(member.user_id)
                              : null
                          }
                        />
                      ))}
                      {members.length === 0 && (
                        <li className="py-2 text-[12px] text-muted">
                          No explicit members yet.
                        </li>
                      )}
                    </ul>

                    <form onSubmit={searchForUsers} className="mt-3">
                      <div className="sys-label mb-1">Add member</div>
                      <div className="flex gap-1.5">
                        <input
                          value={userQuery}
                          onChange={(e) => setUserQuery(e.target.value)}
                          placeholder="Search users"
                          className="min-w-0 flex-1 rounded-md border border-border bg-surface px-2 py-1.5 text-[12px] text-foreground placeholder:text-muted focus:border-[var(--color-brand-400)] focus:outline-none"
                        />
                        <PermissionSelect
                          value={newMemberPermission}
                          onChange={setNewMemberPermission}
                          ariaLabel="New member permission"
                          disabled={memberBusy}
                        />
                        <button
                          type="submit"
                          disabled={memberBusy || !userQuery.trim()}
                          className="rounded-md border border-border bg-base px-2 py-1.5 text-[11.5px] font-medium text-foreground hover:bg-raised disabled:opacity-40"
                        >
                          Search
                        </button>
                      </div>
                      {userResults.length > 0 && (
                        <div className="mt-2 flex flex-col gap-1">
                          {userResults.map((result) => (
                            <button
                              key={result.id}
                              type="button"
                              onClick={() => void addMember(result.id)}
                              className="flex items-center justify-between rounded-md px-2 py-1.5 text-left hover:bg-raised"
                            >
                              <span className="min-w-0">
                                <span className="block truncate text-[13px] font-medium text-foreground">
                                  {result.display_name || result.name}
                                </span>
                                <span className="block truncate text-[11.5px] text-muted">
                                  @{result.name}
                                </span>
                              </span>
                              <span className="text-[11.5px] text-muted">Add</span>
                            </button>
                          ))}
                        </div>
                      )}
                    </form>
                  </>
                )}

                {!membersLoading && !canManageMembers && (
                  <div className="mt-2 rounded-md border border-border bg-surface px-2 py-1.5 text-[12px] text-muted">
                    Only Stash admins can manage members.
                  </div>
                )}
              </div>

              {saving && (
                <div className="mt-2 text-[11px] text-muted">Saving...</div>
              )}
            </>
          )}

          {(shareMessage || memberMessage) && (
            <div className="mt-2 text-[12px] text-muted">
              {memberMessage || shareMessage}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

function OwnerRow({ label, username }: { label: string; username: string }) {
  return (
    <div className="flex items-center gap-2.5 rounded-md border border-border bg-surface px-2 py-1.5 text-[13px]">
      <Avatar label={label} />
      <span className="min-w-0 flex-1">
        <span className="block truncate font-medium text-foreground">{label}</span>
        <span className="block truncate text-[11.5px] text-muted">@{username}</span>
      </span>
      <span className="rounded bg-base px-1.5 py-0.5 text-[10px] uppercase tracking-wide text-muted ring-1 ring-border">
        admin
      </span>
    </div>
  );
}

function MemberRow({
  member,
  isMe,
  busy,
  onPermissionChange,
  onRemove,
}: {
  member: StashMember;
  isMe: boolean;
  busy: boolean;
  onPermissionChange: (permission: StashMemberPermission) => void;
  onRemove: (() => void) | null;
}) {
  const label = member.display_name || member.name;

  return (
    <li className="flex items-center gap-2.5 py-1 text-[13px]">
      <Avatar label={label} />
      <span className="min-w-0 flex-1">
        <span className="block truncate font-medium text-foreground">
          {label}
          {isMe ? <span className="ml-1 text-[10px] text-muted">(you)</span> : null}
        </span>
        <span className="block truncate text-[11.5px] text-muted">@{member.name}</span>
      </span>
      <PermissionSelect
        value={member.permission}
        onChange={onPermissionChange}
        ariaLabel={`Permission for ${member.name}`}
        disabled={busy}
      />
      {onRemove && (
        <button
          type="button"
          onClick={onRemove}
          disabled={busy}
          className="text-[11.5px] text-red-500 hover:underline disabled:opacity-40"
        >
          Remove
        </button>
      )}
    </li>
  );
}

function PermissionSelect({
  value,
  onChange,
  ariaLabel,
  disabled,
}: {
  value: StashMemberPermission;
  onChange: (value: StashMemberPermission) => void;
  ariaLabel: string;
  disabled: boolean;
}) {
  return (
    <select
      aria-label={ariaLabel}
      value={value}
      disabled={disabled}
      onChange={(e) => onChange(e.target.value as StashMemberPermission)}
      className="h-7 rounded border border-border bg-base px-1.5 text-[11.5px] text-foreground outline-none focus:border-[var(--color-brand-400)] disabled:opacity-40"
    >
      {PERMISSION_OPTIONS.map((option) => (
        <option key={option.value} value={option.value}>
          {option.label}
        </option>
      ))}
    </select>
  );
}

function Avatar({ label }: { label: string }) {
  const color = colorFor(label);
  return (
    <span
      className={
        "inline-flex h-6 w-6 flex-shrink-0 items-center justify-center rounded-full text-[9px] font-semibold " +
        color.bg +
        " " +
        color.fg
      }
    >
      {initials(label)}
    </span>
  );
}

function VisOption({
  label,
  hint,
  value,
  current,
  onChange,
}: {
  label: string;
  hint: string;
  value: StashAccess;
  current: StashAccess;
  onChange: (next: StashAccess) => void;
}) {
  const active = value === current;
  return (
    <button
      type="button"
      onClick={() => onChange(value)}
      className={
        "flex items-start gap-2 rounded-md px-2 py-1.5 text-left text-[12px] " +
        (active ? "bg-[var(--color-brand-50)]" : "hover:bg-raised")
      }
    >
      <span
        className={
          "mt-[3px] inline-block h-3 w-3 flex-shrink-0 rounded-full border-2 " +
          (active
            ? "border-[var(--color-brand-600)] bg-[var(--color-brand-500)]"
            : "border-border bg-base")
        }
      />
      <span className="min-w-0">
        <span className="block font-medium text-foreground">{label}</span>
        <span className="block text-[11px] text-muted">{hint}</span>
      </span>
    </button>
  );
}

function colorFor(name: string) {
  let h = 5381;
  for (let i = 0; i < name.length; i++) h = (h * 33 + name.charCodeAt(i)) >>> 0;
  return PALETTE[h % PALETTE.length];
}

function initials(label: string): string {
  return label
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((part) => part[0])
    .join("")
    .toUpperCase();
}

function absoluteUrl(path: string): string {
  if (typeof window === "undefined") return path;
  return `${window.location.origin}${path}`;
}
