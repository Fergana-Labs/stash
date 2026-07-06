"use client";

import {
  FormEvent,
  useCallback,
  useEffect,
  useRef,
  useState,
} from "react";

import { useEscapeKey } from "../../hooks/useEscapeKey";
import {
  listObjectShares,
  setGeneralAccess,
  shareObjectByEmail,
  unshareObject,
  type GeneralAccess,
  type GeneralPermission,
  type ObjectShare,
  type SharedObjectType,
} from "../../lib/api";
import type { User } from "../../lib/types";

type SharePermission = Extract<GeneralPermission, "read" | "comment" | "write">;

const PERMISSIONS: { value: SharePermission; label: string }[] = [
  { value: "read", label: "Can view" },
  { value: "comment", label: "Can comment" },
  { value: "write", label: "Can edit" },
];

export default function ResourceShareButton({
  objectType,
  objectId,
  resourceName,
  resourceUrlPath,
  currentUser,
}: {
  objectType: SharedObjectType;
  objectId: string;
  resourceName: string;
  resourceUrlPath: string;
  currentUser: User;
}) {
  const [open, setOpen] = useState(false);
  const [shares, setShares] = useState<ObjectShare[]>([]);
  const [access, setAccess] = useState<GeneralAccess | null>(null);
  const [email, setEmail] = useState("");
  const [permission, setPermission] = useState<SharePermission>("read");
  const [busy, setBusy] = useState(false);
  const [loadingShares, setLoadingShares] = useState(false);
  const [message, setMessage] = useState("");
  const containerRef = useRef<HTMLDivElement>(null);

  useEscapeKey(open, () => setOpen(false));

  const resourceUrl =
    typeof window === "undefined"
      ? resourceUrlPath
      : `${window.location.origin}${resourceUrlPath}`;
  const displayName = resourceName.trim() || "Untitled";

  const loadShares = useCallback(async () => {
    setLoadingShares(true);
    setMessage("");
    try {
      const res = await listObjectShares(objectType, objectId);
      setShares(res.shares);
      setAccess(res.general_access);
    } catch (e) {
      setMessage(e instanceof Error ? e.message : "Could not load access.");
    } finally {
      setLoadingShares(false);
    }
  }, [objectId, objectType]);

  useEffect(() => {
    if (!open) return;
    void loadShares();
  }, [open, loadShares]);

  useEffect(() => {
    if (!open) return;

    function onDown(event: MouseEvent) {
      if (!containerRef.current) return;
      if (!containerRef.current.contains(event.target as Node)) setOpen(false);
    }

    document.addEventListener("mousedown", onDown);
    return () => document.removeEventListener("mousedown", onDown);
  }, [open]);

  async function addPerson(event: FormEvent) {
    event.preventDefault();
    const trimmedEmail = email.trim();
    if (!trimmedEmail) return;

    setBusy(true);
    setMessage("");
    try {
      await shareObjectByEmail(objectType, objectId, trimmedEmail, permission);
      setEmail("");
      await loadShares();
      setMessage("Access updated.");
    } catch (e) {
      setMessage(e instanceof Error ? e.message : "Could not share resource.");
    } finally {
      setBusy(false);
    }
  }

  async function removePerson(share: ObjectShare) {
    if (!share.principal_id) return;

    setBusy(true);
    setMessage("");
    try {
      await unshareObject(
        objectType,
        objectId,
        share.principal_type,
        share.principal_id,
      );
      await loadShares();
    } catch (e) {
      setMessage(e instanceof Error ? e.message : "Could not remove access.");
    } finally {
      setBusy(false);
    }
  }

  async function changePermission(share: ObjectShare, next: SharePermission) {
    if (!share.email || share.permission === next) return;

    setBusy(true);
    setMessage("");
    try {
      // The share endpoint upserts on conflict, so re-sharing the same email
      // with a new permission updates the existing share or pending invite.
      await shareObjectByEmail(objectType, objectId, share.email, next);
      await loadShares();
      setMessage("Access updated.");
    } catch (e) {
      setMessage(e instanceof Error ? e.message : "Could not update access.");
    } finally {
      setBusy(false);
    }
  }

  async function changeAccess(next: GeneralAccess) {
    setBusy(true);
    setMessage("");
    try {
      await setGeneralAccess(objectType, objectId, next);
      setAccess(next);
      setMessage("Access updated.");
    } catch (e) {
      setMessage(e instanceof Error ? e.message : "Could not update access.");
    } finally {
      setBusy(false);
    }
  }

  async function copyLink() {
    setMessage("");
    try {
      await navigator.clipboard.writeText(resourceUrl);
      setMessage("Link copied.");
    } catch {
      setMessage("Could not copy link.");
    }
  }

  return (
    <div ref={containerRef} className="relative">
      <button
        type="button"
        onClick={() => setOpen((value) => !value)}
        aria-haspopup="dialog"
        aria-expanded={open}
        className="cursor-pointer rounded-md bg-[var(--color-brand-600)] px-2.5 py-1 text-[12.5px] font-medium text-white hover:bg-[var(--color-brand-700)]"
      >
        Share
      </button>

      {open && (
        <div
          role="dialog"
          aria-label={`Share ${displayName}`}
          className="absolute right-0 top-full z-40 mt-1.5 w-[420px] max-w-[calc(100vw-2rem)] rounded-lg border border-border bg-base p-4 shadow-lg"
        >
          <div className="flex items-start justify-between gap-3">
            <div className="min-w-0">
              <h2 className="m-0 truncate text-[18px] font-semibold text-foreground">
                {`Share "${displayName}"`}
              </h2>
            </div>
            <button
              type="button"
              onClick={() => setOpen(false)}
              className="cursor-pointer rounded p-1 text-muted-foreground hover:bg-raised hover:text-foreground"
              aria-label="Close share dialog"
            >
              <svg
                aria-hidden="true"
                className="h-4 w-4"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                strokeWidth="2"
              >
                <path d="M18 6 6 18" />
                <path d="m6 6 12 12" />
              </svg>
            </button>
          </div>

          <form onSubmit={addPerson} className="mt-4">
            <label className="sr-only" htmlFor="resource-share-email">
              Add people
            </label>
            <div className="flex gap-2">
              <input
                id="resource-share-email"
                type="email"
                value={email}
                onChange={(event) => setEmail(event.target.value)}
                placeholder="Add people by email"
                className="min-w-0 flex-1 rounded-md border border-border bg-base px-3 py-2 text-[13px] text-foreground placeholder:text-muted-foreground focus:border-brand focus:outline-none"
              />
              <select
                value={permission}
                onChange={(event) =>
                  setPermission(event.target.value as SharePermission)
                }
                disabled={busy}
                aria-label="Invite permission"
                className="rounded-md border border-border bg-base px-2 py-2 text-[12px] text-foreground"
              >
                {PERMISSIONS.map((option) => (
                  <option key={option.value} value={option.value}>
                    {option.label}
                  </option>
                ))}
              </select>
              <button
                type="submit"
                disabled={busy || !email.trim()}
                className="cursor-pointer rounded-md bg-foreground px-3 py-2 text-[12.5px] font-medium text-background disabled:opacity-45"
              >
                Invite
              </button>
            </div>
          </form>

          <section className="mt-5">
            <h3 className="m-0 text-[13px] font-semibold text-foreground">
              People with access
            </h3>
            <div className="mt-2 flex flex-col gap-2">
              <AccessRow
                label={`${currentUser.display_name || currentUser.name} (you)`}
                sublabel={currentUser.email ?? `@${currentUser.name}`}
                permissionLabel="Owner"
              />

              {loadingShares && (
                <div className="rounded-md border border-border bg-surface px-3 py-2 text-[12.5px] text-muted-foreground">
                  Loading access...
                </div>
              )}

              {!loadingShares &&
                shares.map((share, index) => (
                  <AccessRow
                    key={`${share.principal_id ?? share.email}-${index}`}
                    label={share.label || share.email || "Invited user"}
                    sublabel={
                      share.pending
                        ? "Invited"
                        : share.email ?? share.principal_type
                    }
                    permission={share.permission as SharePermission}
                    onChangePermission={
                      share.email
                        ? (next) => void changePermission(share, next)
                        : undefined
                    }
                    onRemove={
                      share.pending || !share.principal_id
                        ? undefined
                        : () => void removePerson(share)
                    }
                    busy={busy}
                  />
                ))}
            </div>
          </section>

          <section className="mt-5">
            <h3 className="m-0 text-[13px] font-semibold text-foreground">
              General access
            </h3>
            <div className="mt-2 flex items-center gap-3 rounded-md border border-border bg-surface px-3 py-2.5">
              <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-base text-muted-foreground ring-1 ring-border">
                {access === "public" ? <GlobeGlyph /> : <LockGlyph />}
              </span>
              <span className="min-w-0 flex-1">
                <select
                  value={access ?? "restricted"}
                  disabled={busy || access === null}
                  onChange={(event) =>
                    void changeAccess(event.target.value as GeneralAccess)
                  }
                  aria-label="General access"
                  className="rounded-md border border-border bg-base px-1.5 py-1 text-[13px] font-medium text-foreground disabled:opacity-45"
                >
                  <option value="restricted">Restricted</option>
                  <option value="public">Anyone with the link</option>
                </select>
                <span className="mt-1 block truncate text-[12px] text-muted-foreground">
                  {access === "public"
                    ? "Anyone on the internet with the link can view"
                    : "Only people with access can open this link"}
                </span>
              </span>
            </div>
          </section>

          <div className="mt-5 flex items-center justify-between gap-3">
            <button
              type="button"
              onClick={() => void copyLink()}
              className="cursor-pointer rounded-full border border-border bg-base px-4 py-2 text-[13px] font-medium text-foreground hover:bg-raised"
            >
              Copy link
            </button>
            <button
              type="button"
              onClick={() => setOpen(false)}
              className="cursor-pointer rounded-full bg-[var(--color-brand-600)] px-5 py-2 text-[13px] font-medium text-white hover:bg-[var(--color-brand-700)]"
            >
              Done
            </button>
          </div>

          {message && (
            <div className="mt-3 text-[12px] text-muted-foreground" role="status">
              {message}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

function AccessRow({
  label,
  sublabel,
  permissionLabel,
  permission,
  onChangePermission,
  onRemove,
  busy = false,
}: {
  label: string;
  sublabel: string;
  permissionLabel?: string;
  permission?: SharePermission;
  onChangePermission?: (permission: SharePermission) => void;
  onRemove?: () => void;
  busy?: boolean;
}) {
  return (
    <div className="flex items-center gap-2.5 rounded-md px-1 py-1.5">
      <Avatar label={label} />
      <span className="min-w-0 flex-1">
        <span className="block truncate text-[13px] font-medium text-foreground">
          {label}
        </span>
        <span className="block truncate text-[12px] text-muted-foreground">{sublabel}</span>
      </span>
      {onChangePermission && permission ? (
        <select
          value={permission}
          onChange={(event) =>
            onChangePermission(event.target.value as SharePermission)
          }
          disabled={busy}
          aria-label="Change permission"
          className="shrink-0 rounded-md border border-border bg-base px-1.5 py-1 text-[12px] text-foreground disabled:opacity-45"
        >
          {PERMISSIONS.map((option) => (
            <option key={option.value} value={option.value}>
              {option.label}
            </option>
          ))}
        </select>
      ) : (
        <span className="shrink-0 text-[12px] text-muted-foreground">{permissionLabel}</span>
      )}
      {onRemove && (
        <button
          type="button"
          onClick={onRemove}
          disabled={busy}
          className="shrink-0 cursor-pointer text-[12px] text-red-500 hover:underline disabled:opacity-40"
        >
          Remove
        </button>
      )}
    </div>
  );
}

function LockGlyph() {
  return (
    <svg
      aria-hidden="true"
      className="h-4 w-4"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
    >
      <rect x="5" y="11" width="14" height="10" rx="2" />
      <path d="M8 11V8a4 4 0 0 1 8 0v3" />
    </svg>
  );
}

function GlobeGlyph() {
  return (
    <svg
      aria-hidden="true"
      className="h-4 w-4"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
    >
      <circle cx="12" cy="12" r="9" />
      <path d="M3 12h18" />
      <path d="M12 3a13.5 13.5 0 0 1 0 18a13.5 13.5 0 0 1 0-18" />
    </svg>
  );
}

function Avatar({ label }: { label: string }) {
  return (
    <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-brand-100 text-[11px] font-semibold text-[var(--color-brand-700)]">
      {initials(label)}
    </span>
  );
}

function initials(label: string): string {
  return label
    .replace(/\([^)]*\)/g, "")
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((part) => part[0])
    .join("")
    .toUpperCase();
}
