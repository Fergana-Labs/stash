"use client";

import { useEffect, useMemo, useState, type FormEvent, type ReactNode } from "react";
import {
  getStashShare,
  searchUsers,
  updateStash,
  updateStashShare,
  type StashMember,
  type StashMemberPermission,
  type StashShare,
  type WorkspaceStash,
} from "../../lib/api";
import type { UserSearchResult } from "../../lib/types";
import { useEscapeKey } from "../../hooks/useEscapeKey";
import CustomSelect from "../CustomSelect";

type StashAccess = "workspace" | "private" | "public";

const PERMISSION_OPTIONS = [
  { value: "read", label: "Viewer" },
  { value: "write", label: "Editor" },
  { value: "admin", label: "Manager" },
];

const ACCESS_OPTIONS: {
  value: StashAccess;
  label: string;
  hint: string;
}[] = [
  {
    value: "private",
    label: "Restricted",
    hint: "Only people added to this Stash",
  },
  {
    value: "workspace",
    label: "Workspace",
    hint: "Anyone in the owning Workspace",
  },
  {
    value: "public",
    label: "Public",
    hint: "Anyone with the Stash link",
  },
];

const EMPTY_MEMBERS: StashMember[] = [];

export default function StashShareDialog({
  stash,
  workspaceName,
  canWrite,
  canManageAccess,
  open,
  onClose,
  onChanged,
}: {
  stash: WorkspaceStash;
  workspaceName: string;
  canWrite: boolean;
  canManageAccess: boolean;
  open: boolean;
  onClose: () => void;
  onChanged: () => Promise<void>;
}) {
  const [share, setShare] = useState<StashShare | null>(null);
  const [vis, setVis] = useState<StashAccess>(stash.access);
  const [discoverable, setDiscoverable] = useState(stash.discoverable);
  const [query, setQuery] = useState("");
  const [selectedUser, setSelectedUser] = useState<UserSearchResult | null>(null);
  const [suggestions, setSuggestions] = useState<UserSearchResult[]>([]);
  const [permission, setPermission] = useState<StashMemberPermission>("read");
  const [copied, setCopied] = useState(false);
  const [busy, setBusy] = useState("");
  const [message, setMessage] = useState("");

  useEscapeKey(open, onClose);

  useEffect(() => {
    if (!open) return;
    setShare(null);
    setVis(stash.access);
    setDiscoverable(stash.discoverable);
    setQuery("");
    setSelectedUser(null);
    setSuggestions([]);
    setPermission("read");
    setCopied(false);
    setMessage("");

    if (!canManageAccess) return;
    setBusy("load");
    getStashShare(stash.id)
      .then((next) => {
        setShare(next);
        setVis(next.stash.access);
        setDiscoverable(next.stash.discoverable);
      })
      .catch((error) => setMessage(error instanceof Error ? error.message : "Could not load Stash access"))
      .finally(() => setBusy(""));
  }, [canManageAccess, open, stash]);

  useEffect(() => {
    if (!open || !canManageAccess || selectedUser) {
      setSuggestions([]);
      return;
    }

    const trimmed = query.trim();
    if (trimmed.length < 2) {
      setSuggestions([]);
      return;
    }

    let cancelled = false;
    const timer = window.setTimeout(() => {
      searchUsers(trimmed)
        .then((users) => {
          if (!cancelled) setSuggestions(users);
        })
        .catch(() => {
          if (!cancelled) setSuggestions([]);
        });
    }, 150);

    return () => {
      cancelled = true;
      window.clearTimeout(timer);
    };
  }, [canManageAccess, open, query, selectedUser]);

  const currentStash = share?.stash ?? stash;
  const members = share?.members ?? EMPTY_MEMBERS;
  const link = share?.url ?? absoluteUrl(`/stashes/${currentStash.slug}`);
  const workspaceLabel = workspaceName || "the owning Workspace";

  const memberIds = useMemo(() => new Set(members.map((member) => member.user_id)), [members]);
  const visibleSuggestions = suggestions.filter((user) => !memberIds.has(user.id));

  if (!open) return null;

  async function copyLink() {
    await navigator.clipboard.writeText(link);
    setCopied(true);
    window.setTimeout(() => setCopied(false), 1600);
  }

  async function refreshShare(next: StashShare, reloadPage = false) {
    setShare(next);
    setVis(next.stash.access);
    setDiscoverable(next.stash.discoverable);
    if (reloadPage) await onChanged();
  }

  async function addPerson(event: FormEvent) {
    event.preventDefault();
    const username = query.trim();
    if (!selectedUser && !username) return;

    setBusy("add");
    setMessage("");
    try {
      const next = await updateStashShare(stash.id, {
        people: [
          selectedUser
            ? { user_id: selectedUser.id, permission }
            : { username, permission },
        ],
      });
      await refreshShare(next);
      setQuery("");
      setSelectedUser(null);
      setSuggestions([]);
      setPermission("read");
      setMessage("Stash access updated.");
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Could not update Stash access");
    } finally {
      setBusy("");
    }
  }

  async function changeMemberPermission(member: StashMember, nextPermission: string) {
    setBusy(member.user_id);
    setMessage("");
    try {
      const next = await updateStashShare(stash.id, {
        people: [
          {
            user_id: member.user_id,
            permission: nextPermission as StashMemberPermission,
          },
        ],
      });
      await refreshShare(next);
      setMessage("Stash access updated.");
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Could not update Stash access");
    } finally {
      setBusy("");
    }
  }

  async function removeMember(member: StashMember) {
    setBusy(member.user_id);
    setMessage("");
    try {
      const next = await updateStashShare(stash.id, {
        remove_user_ids: [member.user_id],
      });
      await refreshShare(next);
      setMessage("Removed from this Stash.");
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Could not remove Stash access");
    } finally {
      setBusy("");
    }
  }

  async function changeAccess(nextAccess: StashAccess) {
    setVis(nextAccess);
    setBusy("access");
    setMessage("");
    try {
      if (canManageAccess) {
        const next = await updateStashShare(stash.id, { access: nextAccess });
        await refreshShare(next, true);
      } else {
        await updateStash(stash.id, { access: nextAccess });
        await onChanged();
      }
      setMessage("Stash access updated.");
    } catch (error) {
      setVis(currentStash.access);
      setMessage(error instanceof Error ? error.message : "Could not update Stash access");
    } finally {
      setBusy("");
    }
  }

  async function changeDiscoverable(nextDiscoverable: boolean) {
    setDiscoverable(nextDiscoverable);
    setBusy("discover");
    setMessage("");
    try {
      if (canManageAccess) {
        const next = await updateStashShare(stash.id, { discoverable: nextDiscoverable });
        await refreshShare(next, true);
      } else {
        await updateStash(stash.id, { discoverable: nextDiscoverable });
        await onChanged();
      }
      setMessage("Stash access updated.");
    } catch (error) {
      setDiscoverable(currentStash.discoverable);
      setMessage(error instanceof Error ? error.message : "Could not update Discover");
    } finally {
      setBusy("");
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 px-4" onClick={onClose}>
      <div
        className="w-full max-w-lg rounded-xl border border-border bg-base shadow-xl"
        onClick={(event) => event.stopPropagation()}
      >
        <div className="flex items-start justify-between gap-4 border-b border-border px-5 py-4">
          <div className="min-w-0">
            <div className="flex items-center gap-2">
              <h2 className="font-display text-[16px] font-semibold text-foreground">
                Share this Stash
              </h2>
              <span className="rounded-full bg-[var(--color-brand-50)] px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-[var(--color-brand-700)]">
                Stash-level
              </span>
            </div>
            <p className="mt-1 text-[12px] leading-relaxed text-muted">
              People added here can access this Stash without joining {workspaceLabel}.
            </p>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="text-muted hover:text-foreground"
            aria-label="Close Stash sharing"
          >
            x
          </button>
        </div>

        <div className="max-h-[72vh] overflow-y-auto px-5 py-4">
          <section>
            <div className="sys-label mb-1">Stash link</div>
            <div className="flex gap-1.5">
              <input
                readOnly
                value={link}
                className="min-w-0 flex-1 rounded-md border border-border bg-surface px-2 py-1.5 text-[11.5px] font-mono text-foreground"
              />
              <button
                type="button"
                onClick={() => void copyLink()}
                className="rounded-md border border-border bg-base px-2.5 py-1.5 text-[11.5px] font-medium text-foreground hover:bg-raised"
              >
                {copied ? "Copied" : "Copy"}
              </button>
            </div>
          </section>

          {canManageAccess ? (
            <section className="mt-4">
              <div className="sys-label mb-2">People with access to this Stash</div>
              {busy === "load" ? (
                <p className="py-4 text-[12.5px] text-muted">Loading Stash access...</p>
              ) : (
                <div className="flex flex-col gap-2">
                  {share ? (
                    <PersonRow
                      label={share.owner.display_name || share.owner.name}
                      sub={`@${share.owner.name}`}
                      initials={initials(share.owner.display_name || share.owner.name)}
                      control={
                        <span className="rounded bg-surface px-1.5 py-0.5 text-[10px] uppercase tracking-wide text-muted ring-1 ring-border">
                          Owner
                        </span>
                      }
                    />
                  ) : null}

                  {members.map((member) => (
                    <PersonRow
                      key={member.user_id}
                      label={member.display_name || member.name}
                      sub={`@${member.name}`}
                      initials={initials(member.display_name || member.name)}
                      control={
                        <div className="flex items-center gap-1.5">
                          <CustomSelect
                            value={member.permission}
                            options={PERMISSION_OPTIONS}
                            onChange={(nextPermission) => void changeMemberPermission(member, nextPermission)}
                            disabled={busy === member.user_id}
                            className="min-w-[92px] rounded border border-border bg-surface px-1.5 py-1 text-[10px] uppercase tracking-wide text-foreground"
                            menuClassName="text-[11px]"
                            align="right"
                          />
                          <button
                            type="button"
                            onClick={() => void removeMember(member)}
                            disabled={busy === member.user_id}
                            className="px-1 text-[13px] text-muted hover:text-red-500 disabled:opacity-40"
                            title="Remove from this Stash"
                          >
                            x
                          </button>
                        </div>
                      }
                    />
                  ))}
                </div>
              )}

              <form onSubmit={addPerson} className="mt-3">
                <div className="flex gap-2">
                  <div className="relative min-w-0 flex-1">
                    <input
                      value={query}
                      onChange={(event) => {
                        setQuery(event.target.value);
                        setSelectedUser(null);
                      }}
                      placeholder="Add people by username"
                      className="w-full rounded-md border border-border bg-surface px-2.5 py-1.5 text-[12.5px] text-foreground placeholder:text-muted focus:border-[var(--color-brand-400)] focus:outline-none"
                    />
                    {visibleSuggestions.length > 0 ? (
                      <div className="absolute left-0 right-0 top-full z-[60] mt-1 overflow-hidden rounded-md border border-border bg-surface py-1 shadow-lg">
                        {visibleSuggestions.map((user) => (
                          <button
                            key={user.id}
                            type="button"
                            onClick={() => {
                              setSelectedUser(user);
                              setQuery(user.name);
                              setSuggestions([]);
                            }}
                            className="flex w-full items-center gap-2 px-2.5 py-1.5 text-left text-[12px] text-foreground hover:bg-raised"
                          >
                            <Avatar label={user.display_name || user.name} />
                            <span className="min-w-0 flex-1 truncate">
                              {user.display_name || user.name}
                            </span>
                            <span className="text-[11px] text-muted">@{user.name}</span>
                          </button>
                        ))}
                      </div>
                    ) : null}
                  </div>
                  <CustomSelect
                    value={permission}
                    options={PERMISSION_OPTIONS}
                    onChange={(next) => setPermission(next as StashMemberPermission)}
                    className="min-w-[92px] rounded-md border border-border bg-surface px-2 py-1.5 text-[11px] text-foreground"
                    menuClassName="text-[11px]"
                    align="right"
                  />
                  <button
                    type="submit"
                    disabled={busy === "add" || !query.trim()}
                    className="rounded-md bg-[var(--color-brand-600)] px-3 py-1.5 text-[12px] font-medium text-white hover:bg-[var(--color-brand-700)] disabled:opacity-40"
                  >
                    Add
                  </button>
                </div>
              </form>
            </section>
          ) : null}

          {canWrite ? (
            <section className="mt-5 border-t border-border-subtle pt-4">
              <div className="sys-label mb-2">General Stash access</div>
              <div className="flex flex-col gap-1.5">
                {ACCESS_OPTIONS.map((option) => (
                  <button
                    key={option.value}
                    type="button"
                    disabled={busy === "access"}
                    onClick={() => void changeAccess(option.value)}
                    className={
                      "flex items-center justify-between gap-3 rounded-md border px-3 py-2 text-left disabled:opacity-50 " +
                      (vis === option.value
                        ? "border-[var(--color-brand-500)] bg-[var(--color-brand-50)]"
                        : "border-border bg-surface hover:bg-raised")
                    }
                  >
                    <span className="min-w-0">
                      <span className="block text-[12.5px] font-medium text-foreground">
                        {option.label}
                      </span>
                      <span className="block text-[11.5px] text-muted">{option.hint}</span>
                    </span>
                    <span
                      className={
                        "h-2.5 w-2.5 rounded-full border " +
                        (vis === option.value
                          ? "border-[var(--color-brand-600)] bg-[var(--color-brand-600)]"
                          : "border-border")
                      }
                    />
                  </button>
                ))}
              </div>

              {vis === "public" ? (
                <label className="mt-3 flex cursor-pointer items-center gap-2 rounded-md border border-border bg-surface px-3 py-2">
                  <input
                    type="checkbox"
                    checked={discoverable}
                    disabled={busy === "discover"}
                    onChange={(event) => void changeDiscoverable(event.target.checked)}
                  />
                  <span className="text-[12px] text-foreground">List on Discover</span>
                </label>
              ) : null}
            </section>
          ) : null}

          {message ? <p className="mt-3 text-[12px] text-muted">{message}</p> : null}
        </div>
      </div>
    </div>
  );
}

function PersonRow({
  label,
  sub,
  initials,
  control,
}: {
  label: string;
  sub: string;
  initials: string;
  control: ReactNode;
}) {
  return (
    <div className="flex items-center gap-2.5 text-[13px]">
      <span className="inline-flex h-7 w-7 items-center justify-center rounded-full bg-emerald-100 text-[10px] font-semibold text-emerald-800">
        {initials}
      </span>
      <span className="min-w-0 flex-1">
        <span className="block truncate font-medium text-foreground">{label}</span>
        <span className="block truncate text-[11px] text-muted">{sub}</span>
      </span>
      {control}
    </div>
  );
}

function Avatar({ label }: { label: string }) {
  return (
    <span className="inline-flex h-6 w-6 items-center justify-center rounded-full bg-indigo-100 text-[9px] font-semibold text-indigo-800">
      {initials(label)}
    </span>
  );
}

function initials(label: string): string {
  return label.trim().slice(0, 2).toUpperCase() || "US";
}

function absoluteUrl(path: string): string {
  if (typeof window === "undefined") return path;
  return `${window.location.origin}${path}`;
}
