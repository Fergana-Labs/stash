"use client";

import { FormEvent, useCallback, useEffect, useRef, useState } from "react";
import { useEscapeKey } from "../../hooks/useEscapeKey";
import {
  ApiError,
  getMe,
  listObjectShares,
  shareObjectByEmail,
  unshareObject,
  updateSkill,
  type ObjectShare,
  type PublicSkillDetail,
  type SkillGeneralPermission,
} from "../../lib/api";
import { resetSkillNavigationCache } from "../../lib/skillNavigationCache";

type SkillVisibility = "private" | "workspace" | "public";
type HandoffStatus = "idle" | "copying" | "copied" | "error";

type SharePermission = "read" | "write";

const PERMISSION_OPTIONS: { value: SharePermission; label: string }[] = [
  { value: "read", label: "Can view" },
  { value: "write", label: "Can edit" },
];

const VISIBILITY_OPTIONS: { value: SkillVisibility; label: string }[] = [
  { value: "private", label: "Private" },
  { value: "workspace", label: "Workspace" },
  { value: "public", label: "Public" },
];

const WORKSPACE_PERMISSION_OPTIONS: { value: SkillGeneralPermission; label: string }[] = [
  { value: "none", label: "No access" },
  { value: "read", label: "Can view" },
  { value: "write", label: "Can edit" },
];

const PUBLIC_PERMISSION_OPTIONS: { value: SkillGeneralPermission; label: string }[] = [
  { value: "none", label: "No access" },
  { value: "read", label: "Can view" },
  { value: "write", label: "Can edit" },
];

const PALETTE = [
  { bg: "bg-rose-200", fg: "text-rose-800" },
  { bg: "bg-orange-200", fg: "text-orange-800" },
  { bg: "bg-emerald-200", fg: "text-emerald-800" },
  { bg: "bg-amber-200", fg: "text-amber-900" },
  { bg: "bg-sky-200", fg: "text-sky-800" },
  { bg: "bg-teal-200", fg: "text-teal-800" },
];

function visibilityForPermissions(
  workspacePermission: SkillGeneralPermission,
  publicPermission: SkillGeneralPermission
): SkillVisibility {
  if (publicPermission !== "none") return "public";
  if (workspacePermission !== "none") return "workspace";
  return "private";
}

function permissionsForVisibility(
  visibility: SkillVisibility,
  workspacePermission: SkillGeneralPermission,
  publicPermission: SkillGeneralPermission
): {
  workspacePermission: SkillGeneralPermission;
  publicPermission: SkillGeneralPermission;
} {
  if (visibility === "private") {
    return { workspacePermission: "none", publicPermission: "none" };
  }
  if (visibility === "workspace") {
    return {
      workspacePermission: workspacePermission === "none" ? "read" : workspacePermission,
      publicPermission: "none",
    };
  }
  return {
    workspacePermission: workspacePermission === "none" ? "read" : workspacePermission,
    publicPermission: publicPermission === "none" ? "read" : publicPermission,
  };
}

export default function SkillShareButton({
  skill,
  canWrite,
  onChanged,
}: {
  skill: PublicSkillDetail["skill"];
  canWrite: boolean;
  onChanged: () => Promise<void>;
}) {
  const [open, setOpen] = useState(false);
  const [copied, setCopied] = useState(false);
  const [workspacePermission, setWorkspacePermission] =
    useState<SkillGeneralPermission>(skill.workspace_permission);
  const [publicPermission, setPublicPermission] =
    useState<SkillGeneralPermission>(skill.public_permission);
  const [discoverable, setDiscoverable] = useState(skill.discoverable);
  const [saving, setSaving] = useState(false);
  const [shareMessage, setShareMessage] = useState("");
  const [handoffStatus, setHandoffStatus] = useState<HandoffStatus>("idle");
  const [handoffMessage, setHandoffMessage] = useState("");
  const [members, setMembers] = useState<ObjectShare[]>([]);
  const [meId, setMeId] = useState<string | null>(null);
  const [membersLoading, setMembersLoading] = useState(false);
  const [canManageMembers, setCanManageMembers] = useState(false);
  const [memberBusy, setMemberBusy] = useState(false);
  const [memberMessage, setMemberMessage] = useState("");
  const [memberEmail, setMemberEmail] = useState("");
  const [newMemberPermission, setNewMemberPermission] = useState<SharePermission>("read");
  const popoverRef = useRef<HTMLDivElement>(null);

  useEscapeKey(open, () => setOpen(false));

  useEffect(() => {
    setWorkspacePermission(skill.workspace_permission);
    setPublicPermission(skill.public_permission);
    setDiscoverable(skill.discoverable);
  }, [skill.workspace_permission, skill.public_permission, skill.discoverable]);

  const loadMembers = useCallback(async () => {
    setMembersLoading(true);
    setMemberMessage("");
    try {
      const [shares, me] = await Promise.all([
        listObjectShares("skill", skill.id),
        getMe(),
      ]);
      setMembers(shares.filter((share) => share.principal_type === "user"));
      setMeId(me.id);
      setCanManageMembers(true);
    } catch (e) {
      if (e instanceof ApiError && (e.status === 403 || e.status === 404)) {
        setMembers([]);
        setCanManageMembers(false);
        return;
      }
      setMemberMessage(e instanceof Error ? e.message : "Failed to load members.");
    } finally {
      setMembersLoading(false);
    }
  }, [skill.id]);

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
    setMemberEmail("");
    setCopied(false);
    void loadMembers();
  }, [open, canWrite, loadMembers]);

  async function copyLink() {
    try {
      await navigator.clipboard.writeText(absoluteUrl(`/skills/${skill.slug}`));
      setCopied(true);
      setShareMessage("Link copied.");
      window.setTimeout(() => setCopied(false), 1600);
    } catch {
      setShareMessage("Failed to copy link.");
    }
  }

  async function copyAgentHandoffLink() {
    setOpen(false);
    setHandoffStatus("copying");
    setHandoffMessage("");
    try {
      if (publicPermission === "none") {
        if (!canWrite) {
          throw new Error("Only skill editors can create public agent links.");
        }
        const updated = await updateSkill(skill.id, {
          workspace_permission:
            workspacePermission === "none" ? "read" : workspacePermission,
          public_permission: "read",
          discoverable: false,
        });
        setWorkspacePermission(updated.workspace_permission);
        setPublicPermission(updated.public_permission);
        setDiscoverable(updated.discoverable);
        resetSkillNavigationCache();
      }

      await navigator.clipboard.writeText(agentHandoffUrl(skill.slug));
      setHandoffStatus("copied");
      window.setTimeout(() => setHandoffStatus("idle"), 1600);
    } catch (e) {
      setHandoffStatus("error");
      setHandoffMessage(e instanceof Error ? e.message : "Could not copy agent link.");
      window.setTimeout(() => {
        setHandoffStatus("idle");
        setHandoffMessage("");
      }, 3000);
    }
  }

  async function applyGeneralAccess(
    nextWorkspacePermission: SkillGeneralPermission,
    nextPublicPermission: SkillGeneralPermission,
  ) {
    const nextDiscoverable = nextPublicPermission === "none" ? false : discoverable;
    setSaving(true);
    setShareMessage("");
    try {
      const updated = await updateSkill(skill.id, {
        workspace_permission: nextWorkspacePermission,
        public_permission: nextPublicPermission,
        discoverable: nextDiscoverable,
      });
      setWorkspacePermission(updated.workspace_permission);
      setPublicPermission(updated.public_permission);
      setDiscoverable(updated.discoverable);
      resetSkillNavigationCache();
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
      const updated = await updateSkill(skill.id, {
        workspace_permission: workspacePermission,
        public_permission: publicPermission,
        discoverable: nextDiscoverable,
      });
      setWorkspacePermission(updated.workspace_permission);
      setPublicPermission(updated.public_permission);
      setDiscoverable(updated.discoverable);
      resetSkillNavigationCache();
      await onChanged();
    } catch (e) {
      setShareMessage(e instanceof Error ? e.message : "Could not update Discover.");
    } finally {
      setSaving(false);
    }
  }

  async function addMember(e: FormEvent) {
    e.preventDefault();
    const email = memberEmail.trim();
    if (!email) return;

    setMemberBusy(true);
    setMemberMessage("");
    try {
      await shareObjectByEmail("skill", skill.id, email, newMemberPermission);
      await loadMembers();
      setMemberEmail("");
      setMemberMessage("Added.");
      resetSkillNavigationCache();
    } catch (e) {
      setMemberMessage(e instanceof Error ? e.message : "Could not add member.");
    } finally {
      setMemberBusy(false);
    }
  }

  async function changeMemberPermission(share: ObjectShare, permission: SharePermission) {
    if (!share.email) return;

    setMemberBusy(true);
    setMemberMessage("");
    try {
      await shareObjectByEmail("skill", skill.id, share.email, permission);
      await loadMembers();
      setMemberMessage("Updated.");
      resetSkillNavigationCache();
    } catch (e) {
      setMemberMessage(e instanceof Error ? e.message : "Could not update member.");
    } finally {
      setMemberBusy(false);
    }
  }

  async function deleteMember(share: ObjectShare) {
    if (!share.principal_id) return;
    if (!confirm("Remove this person from the skill?")) return;

    setMemberBusy(true);
    setMemberMessage("");
    try {
      await unshareObject("skill", skill.id, "user", share.principal_id);
      await loadMembers();
      resetSkillNavigationCache();
    } catch (e) {
      setMemberMessage(e instanceof Error ? e.message : "Could not remove member.");
    } finally {
      setMemberBusy(false);
    }
  }

  const ownerLabel = skill.owner_display_name || skill.owner_name;
  const visibility = visibilityForPermissions(workspacePermission, publicPermission);

  function applyVisibility(nextVisibility: SkillVisibility) {
    const next = permissionsForVisibility(
      nextVisibility,
      workspacePermission,
      publicPermission
    );
    void applyGeneralAccess(next.workspacePermission, next.publicPermission);
  }

  return (
    <div ref={popoverRef} className="relative flex items-center gap-1.5">
      <button
        type="button"
        onClick={() => void copyAgentHandoffLink()}
        disabled={handoffStatus === "copying"}
        aria-label="Copy agent handoff link"
        title="Copy an agent-readable public link"
        className="inline-flex min-w-[72px] items-center justify-center rounded-md bg-surface px-2.5 py-1 text-[12.5px] font-medium text-dim ring-1 ring-inset ring-border hover:bg-raised hover:text-foreground disabled:opacity-50"
      >
        {handoffStatus === "copying"
          ? "Copying"
          : handoffStatus === "copied"
            ? "Copied"
            : "Agent Handoff"}
      </button>
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        aria-haspopup="dialog"
        aria-expanded={open}
        className="rounded-md bg-[var(--color-brand-600)] px-2.5 py-1 text-[12.5px] font-medium text-white hover:bg-[var(--color-brand-700)]"
      >
        Share
      </button>
      {handoffMessage && !open && (
        <div className="absolute right-0 top-full z-40 mt-1.5 max-w-[280px] rounded-md border border-border bg-base px-2 py-1.5 text-[12px] text-muted shadow-lg">
          {handoffMessage}
        </div>
      )}
      {open && (
        <div
          role="dialog"
          aria-label={`Share ${skill.title}`}
          className="absolute right-0 top-full z-40 mt-1.5 w-[360px] rounded-lg border border-border bg-base p-3 shadow-lg"
        >
          <div className="sys-label mb-1">Public URL</div>
          <div className="flex gap-1.5">
            <input
              readOnly
              value={absoluteUrl(`/skills/${skill.slug}`)}
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
              <div className="sys-label mb-1 mt-3">General access</div>
              <div className="flex flex-col gap-1">
                <VisibilityAccessRow
                  label="Visibility"
                  hint="Choose who can open this skill"
                  value={visibility}
                  options={VISIBILITY_OPTIONS}
                  onChange={applyVisibility}
                />
                <GeneralAccessRow
                  label="Workspace"
                  hint="Anyone in the owning workspace"
                  value={workspacePermission}
                  options={WORKSPACE_PERMISSION_OPTIONS}
                  onChange={(permission) =>
                    void applyGeneralAccess(permission, publicPermission)
                  }
                />
                <GeneralAccessRow
                  label="Public"
                  hint="Anyone with the URL"
                  value={publicPermission}
                  options={PUBLIC_PERMISSION_OPTIONS}
                  onChange={(permission) =>
                    void applyGeneralAccess(workspacePermission, permission)
                  }
                />
              </div>

              {publicPermission !== "none" && (
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
                <OwnerRow label={ownerLabel} username={skill.owner_name} />

                {membersLoading && (
                  <div className="mt-2 rounded-md border border-border bg-surface px-2 py-1.5 text-[12px] text-muted">
                    Loading members...
                  </div>
                )}

                {!membersLoading && canManageMembers && (
                  <>
                    <ul className="mt-2 max-h-44 overflow-y-auto pr-1">
                      {members.map((member, index) => (
                        <MemberRow
                          key={member.principal_id ?? `${member.email}-${index}`}
                          member={member}
                          isMe={member.principal_id === meId}
                          busy={memberBusy}
                          onPermissionChange={(permission) =>
                            void changeMemberPermission(member, permission)
                          }
                          onRemove={
                            member.principal_id && member.principal_id !== meId
                              ? () => void deleteMember(member)
                              : null
                          }
                        />
                      ))}
                      {members.length === 0 && (
                        <li className="py-2 text-[12px] text-muted">
                          Not shared with anyone yet.
                        </li>
                      )}
                    </ul>

                    <form onSubmit={addMember} className="mt-3">
                      <div className="sys-label mb-1">Share with people</div>
                      <div className="flex gap-1.5">
                        <input
                          type="email"
                          value={memberEmail}
                          onChange={(e) => setMemberEmail(e.target.value)}
                          placeholder="Add people by email"
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
                          disabled={memberBusy || !memberEmail.trim()}
                          className="rounded-md border border-border bg-base px-2 py-1.5 text-[11.5px] font-medium text-foreground hover:bg-raised disabled:opacity-40"
                        >
                          Invite
                        </button>
                      </div>
                    </form>
                  </>
                )}

                {!membersLoading && !canManageMembers && (
                  <div className="mt-2 rounded-md border border-border bg-surface px-2 py-1.5 text-[12px] text-muted">
                    Only workspace members can manage sharing.
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
        owner
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
  member: ObjectShare;
  isMe: boolean;
  busy: boolean;
  onPermissionChange: (permission: SharePermission) => void;
  onRemove: (() => void) | null;
}) {
  const label = member.label || member.email || "Invited user";

  return (
    <li className="flex items-center gap-2.5 py-1 text-[13px]">
      <Avatar label={label} />
      <span className="min-w-0 flex-1">
        <span className="block truncate font-medium text-foreground">
          {label}
          {isMe ? <span className="ml-1 text-[10px] text-muted">(you)</span> : null}
        </span>
        <span className="block truncate text-[11.5px] text-muted">
          {member.pending ? "Invited" : member.email ?? ""}
        </span>
      </span>
      <PermissionSelect
        value={member.permission === "write" ? "write" : "read"}
        onChange={onPermissionChange}
        ariaLabel={`Permission for ${label}`}
        disabled={busy || !member.email}
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
  value: SharePermission;
  onChange: (value: SharePermission) => void;
  ariaLabel: string;
  disabled: boolean;
}) {
  return (
    <select
      aria-label={ariaLabel}
      value={value}
      disabled={disabled}
      onChange={(e) => onChange(e.target.value as SharePermission)}
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

function VisibilityAccessRow({
  label,
  hint,
  value,
  options,
  onChange,
}: {
  label: string;
  hint: string;
  value: SkillVisibility;
  options: { value: SkillVisibility; label: string }[];
  onChange: (next: SkillVisibility) => void;
}) {
  return (
    <div className="flex items-center gap-2 rounded-md bg-surface px-2 py-1.5 text-[12px]">
      <span className="min-w-0">
        <span className="block font-medium text-foreground">{label}</span>
        <span className="block text-[11px] text-muted">{hint}</span>
      </span>
      <select
        value={value}
        onChange={(e) => onChange(e.target.value as SkillVisibility)}
        className="ml-auto h-7 rounded border border-border bg-base px-1.5 text-[11.5px] text-foreground outline-none focus:border-[var(--color-brand-400)]"
        aria-label={label}
      >
        {options.map((option) => (
          <option key={option.value} value={option.value}>
            {option.label}
          </option>
        ))}
      </select>
    </div>
  );
}

function GeneralAccessRow({
  label,
  hint,
  value,
  options,
  onChange,
}: {
  label: string;
  hint: string;
  value: SkillGeneralPermission;
  options: { value: SkillGeneralPermission; label: string }[];
  onChange: (next: SkillGeneralPermission) => void;
}) {
  return (
    <div className="flex items-center gap-2 rounded-md bg-surface px-2 py-1.5 text-[12px]">
      <span className="min-w-0">
        <span className="block font-medium text-foreground">{label}</span>
        <span className="block text-[11px] text-muted">{hint}</span>
      </span>
      <select
        value={value}
        onChange={(e) => onChange(e.target.value as SkillGeneralPermission)}
        className="ml-auto h-7 rounded border border-border bg-base px-1.5 text-[11.5px] text-foreground outline-none focus:border-[var(--color-brand-400)]"
        aria-label={`${label} access`}
      >
        {options.map((option) => (
          <option key={option.value} value={option.value}>
            {option.label}
          </option>
        ))}
      </select>
    </div>
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

function agentHandoffUrl(slug: string): string {
  return absoluteUrl(`/api/v1/skills/${slug}?format=text`);
}
