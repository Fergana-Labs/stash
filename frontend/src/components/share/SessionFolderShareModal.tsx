"use client";

import { useCallback, useEffect, useState } from "react";

import {
  type GeneralPermission,
  type ObjectShare,
  type SessionFolder,
  type SessionFolderVisibility,
  listObjectShares,
  revokePendingShareInvite,
  shareObjectByEmail,
  unshareObject,
  updateSessionFolder,
} from "../../lib/api";

// Two-state visibility: Private (only you, plus anyone you invite below) vs
// Public (anyone with the link). Inviting people on a private folder surfaces it
// as "Shared" in the folder list — that's derived, not a third toggle here.
const VISIBILITIES: { key: SessionFolderVisibility; label: string; hint: string }[] = [
  { key: "private", label: "Private", hint: "Only you and people you invite" },
  { key: "public", label: "Public", hint: "Anyone with the link" },
];

function permissionsFor(v: SessionFolderVisibility): {
  workspace_permission: GeneralPermission;
  public_permission: GeneralPermission;
} {
  if (v === "public") return { workspace_permission: "read", public_permission: "read" };
  return { workspace_permission: "read", public_permission: "none" };
}

export default function SessionFolderShareModal({
  folder,
  onClose,
  onChanged,
}: {
  folder: SessionFolder;
  onClose: () => void;
  onChanged: () => void;
}) {
  const [visibility, setVisibility] = useState<SessionFolderVisibility>(folder.access);
  const [shares, setShares] = useState<ObjectShare[]>([]);
  const [email, setEmail] = useState("");
  const [permission, setPermission] = useState<GeneralPermission>("read");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [copied, setCopied] = useState(false);

  const publicUrl =
    typeof window !== "undefined" ? `${window.location.origin}/session-folders/${folder.slug}` : "";

  const loadShares = useCallback(async () => {
    try {
      setShares(await listObjectShares("session_folder", folder.id));
    } catch {
      /* owner-only; ignore on shared views */
    }
  }, [folder.id]);

  useEffect(() => {
    loadShares();
  }, [loadShares]);

  async function changeVisibility(next: SessionFolderVisibility) {
    setVisibility(next);
    setBusy(true);
    setError("");
    try {
      await updateSessionFolder(folder.id, permissionsFor(next));
      onChanged();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not update visibility");
    } finally {
      setBusy(false);
    }
  }

  async function addPerson(e: React.FormEvent) {
    e.preventDefault();
    if (!email.trim()) return;
    setBusy(true);
    setError("");
    try {
      await shareObjectByEmail("session_folder", folder.id, email.trim(), permission);
      setEmail("");
      await loadShares();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not share");
    } finally {
      setBusy(false);
    }
  }

  async function removePerson(share: ObjectShare) {
    if (share.pending && share.email) {
      await revokePendingShareInvite("session_folder", folder.id, share.email);
      await loadShares();
      return;
    }
    if (!share.principal_id) return;
    await unshareObject(
      "session_folder",
      folder.id,
      share.principal_type,
      share.principal_id,
    );
    await loadShares();
  }

  async function copyLink() {
    await navigator.clipboard.writeText(publicUrl);
    setCopied(true);
    window.setTimeout(() => setCopied(false), 1500);
  }

  return (
    <div
      className="fixed inset-0 z-[60] flex cursor-pointer items-center justify-center bg-black/40 p-4"
      onClick={onClose}
    >
      <div
        className="w-full max-w-[440px] rounded-xl border border-border bg-base p-5 shadow-xl"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-start justify-between">
          <div>
            <h2 className="m-0 font-display text-[17px] font-bold text-foreground">Share folder</h2>
            <p className="mt-0.5 text-[12.5px] text-muted">{folder.name}</p>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="cursor-pointer text-[20px] leading-none text-muted hover:text-foreground"
            aria-label="Close"
          >
            ×
          </button>
        </div>

        {error && <p className="mt-3 text-[12px] text-rose-500">{error}</p>}

        <div className="mt-4">
          <label className="text-[11px] font-semibold uppercase tracking-wide text-muted">
            Visibility
          </label>
          <div className="mt-1.5 inline-flex w-full gap-0.5 rounded-lg border border-border bg-surface p-[3px]">
            {VISIBILITIES.map((v) => (
              <button
                key={v.key}
                type="button"
                disabled={busy}
                onClick={() => changeVisibility(v.key)}
                className={
                  "flex-1 cursor-pointer rounded-md px-2 py-[5px] text-[12.5px] " +
                  (visibility === v.key
                    ? "bg-raised font-semibold text-foreground"
                    : "text-muted hover:text-foreground")
                }
              >
                {v.label}
              </button>
            ))}
          </div>
          <p className="mt-1.5 text-[11.5px] text-muted">
            {VISIBILITIES.find((v) => v.key === visibility)?.hint}
          </p>
        </div>

        {visibility === "public" && (
          <div className="mt-3 flex items-center gap-2 rounded-lg border border-border bg-surface px-2.5 py-1.5">
            <span className="min-w-0 flex-1 truncate text-[12px] text-dim">{publicUrl}</span>
            <button
              type="button"
              onClick={copyLink}
              className="shrink-0 cursor-pointer rounded-md bg-[var(--color-brand-600)] px-2.5 py-1 text-[12px] font-medium text-white hover:bg-[var(--color-brand-700)]"
            >
              {copied ? "Copied" : "Copy link"}
            </button>
          </div>
        )}

        <div className="mt-5">
          <label className="text-[11px] font-semibold uppercase tracking-wide text-muted">
            Invite people
          </label>
          <form onSubmit={addPerson} className="mt-1.5 flex gap-2">
            <input
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="email@company.com"
              className="min-w-0 flex-1 rounded-md border border-border bg-base px-2.5 py-1.5 text-[13px] text-foreground placeholder:text-muted focus:border-brand focus:outline-none"
            />
            <select
              value={permission}
              onChange={(e) => setPermission(e.target.value as GeneralPermission)}
              className="rounded-md border border-border bg-base px-2 py-1.5 text-[12.5px] text-foreground"
            >
              <option value="read">Can view</option>
              <option value="write">Can edit</option>
            </select>
            <button
              type="submit"
              disabled={busy || !email.trim()}
              className="cursor-pointer rounded-md bg-foreground px-3 py-1.5 text-[12.5px] font-medium text-background disabled:opacity-45"
            >
              Invite
            </button>
          </form>

          {shares.length > 0 && (
            <ul className="mt-3 flex flex-col gap-1.5">
              {shares.map((s, i) => (
                <li
                  key={`${s.principal_id ?? s.email}-${i}`}
                  className="flex items-center justify-between gap-2 text-[12.5px]"
                >
                  <span className="min-w-0 truncate text-foreground">
                    {s.label || s.email}
                    {s.pending && <span className="ml-1.5 text-[11px] text-muted">invited</span>}
                  </span>
                  <span className="flex shrink-0 items-center gap-2">
                    <span className="text-[11.5px] text-muted">
                      {s.permission === "write" ? "Can edit" : "Can view"}
                    </span>
                    <button
                      type="button"
                      onClick={() => void removePerson(s)}
                      className="cursor-pointer text-[11.5px] text-rose-500 hover:underline"
                    >
                      Remove
                    </button>
                  </span>
                </li>
              ))}
            </ul>
          )}
        </div>
      </div>
    </div>
  );
}
