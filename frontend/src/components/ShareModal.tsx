"use client";

import { useEffect, useState } from "react";
import {
  createStashShareLink,
  listStashShareLinks,
  revokeStashShareLink,
  type ShareLink,
} from "../lib/api";

interface ShareModalProps {
  stashId: string;
  stashName: string;
  open: boolean;
  onClose: () => void;
}

const TTL_OPTIONS: { label: string; days: number | null }[] = [
  { label: "7 days", days: 7 },
  { label: "14 days", days: 14 },
  { label: "30 days", days: 30 },
  { label: "Never expires", days: null },
];

type TargetType = "workspace" | "session" | "page" | "folder" | "file";

export default function ShareModal({ stashId, stashName, open, onClose }: ShareModalProps) {
  const [ttlDays, setTtlDays] = useState<number | null>(14);
  const [permission, setPermission] = useState<"view" | "edit">("view");
  const [targetType, setTargetType] = useState<TargetType>("workspace");
  const [targetId, setTargetId] = useState<string>("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [links, setLinks] = useState<ShareLink[]>([]);
  const [copiedId, setCopiedId] = useState<string | null>(null);

  useEffect(() => {
    if (!open) return;
    listStashShareLinks(stashId).then(setLinks).catch(() => {});
  }, [open, stashId]);

  if (!open) return null;

  async function mint() {
    setBusy(true);
    setError("");
    try {
      // Workspace target: target_id is the stash itself. Other targets
      // need a UUID — paste it for now until per-resource Share buttons
      // land that pre-fill this field.
      if (targetType !== "workspace" && !targetId.trim()) {
        throw new Error(`Paste the ${targetType} UUID to share`);
      }
      const link = await createStashShareLink(stashId, {
        permission,
        ttl_days: ttlDays,
        target_type: targetType,
        target_id: targetType === "workspace" ? stashId : targetId.trim(),
      });
      setLinks((l) => [link, ...l]);
      await navigator.clipboard.writeText(link.url).catch(() => {});
      setCopiedId(link.token);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to create link");
    } finally {
      setBusy(false);
    }
  }

  async function revoke(token: string) {
    if (!confirm("Revoke this share link? Anyone with the URL will get a 404.")) return;
    try {
      await revokeStashShareLink(stashId, token);
      setLinks((l) => l.filter((x) => x.token !== token));
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to revoke");
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 px-4">
      <div className="w-full max-w-lg rounded-2xl border border-border bg-base shadow-xl">
        <div className="flex items-center justify-between border-b border-border-subtle px-5 py-3">
          <h2 className="font-display text-[15px] font-semibold text-foreground">
            Share {stashName}
          </h2>
          <button onClick={onClose} className="text-muted hover:text-foreground">
            ✕
          </button>
        </div>

        <div className="px-5 py-4">
          <div className="mb-3 text-[12px]">
            <label className="flex flex-col gap-1">
              <span className="font-medium text-foreground">What to share</span>
              <select
                value={targetType}
                onChange={(e) => {
                  setTargetType(e.target.value as TargetType);
                  setTargetId("");
                }}
                className="rounded-md border border-border bg-surface px-2 py-1.5"
              >
                <option value="workspace">The whole stash</option>
                <option value="session">A specific session</option>
                <option value="page">A specific page</option>
                <option value="folder">A specific folder</option>
                <option value="file">A specific file</option>
              </select>
            </label>
            {targetType !== "workspace" && (
              <label className="mt-2 flex flex-col gap-1">
                <span className="font-medium text-foreground">{targetType} UUID</span>
                <input
                  type="text"
                  value={targetId}
                  onChange={(e) => setTargetId(e.target.value)}
                  placeholder={`Paste the ${targetType} UUID`}
                  className="rounded-md border border-border bg-surface px-2 py-1.5 font-mono text-[11px]"
                />
                <span className="text-[10.5px] text-muted">
                  Per-resource Share buttons coming soon — for now, paste from the URL.
                </span>
              </label>
            )}
          </div>
          <div className="mb-4 grid grid-cols-2 gap-3 text-[12px]">
            <label className="flex flex-col gap-1">
              <span className="font-medium text-foreground">Expires</span>
              <select
                value={ttlDays ?? "never"}
                onChange={(e) =>
                  setTtlDays(e.target.value === "never" ? null : Number(e.target.value))
                }
                className="rounded-md border border-border bg-surface px-2 py-1.5"
              >
                {TTL_OPTIONS.map((o) => (
                  <option key={o.label} value={o.days ?? "never"}>
                    {o.label}
                  </option>
                ))}
              </select>
            </label>
            <label className="flex flex-col gap-1">
              <span className="font-medium text-foreground">Permission</span>
              <select
                value={permission}
                onChange={(e) =>
                  setPermission(e.target.value as "view" | "edit")
                }
                className="rounded-md border border-border bg-surface px-2 py-1.5"
              >
                <option value="view">View only</option>
                <option value="edit">Allow edit</option>
              </select>
            </label>
          </div>

          <button
            onClick={mint}
            disabled={busy}
            className="w-full rounded-md bg-brand px-3 py-2 text-[13px] font-medium text-white hover:bg-[var(--color-brand-hover)] disabled:opacity-40"
          >
            {busy ? "Creating…" : "Create share link"}
          </button>

          {error && (
            <div className="mt-3 rounded-lg border border-red-300/40 bg-red-500/10 px-3 py-2 text-[12px] text-red-400">
              {error}
            </div>
          )}

          {links.length > 0 && (
            <div className="mt-5">
              <div className="mb-2 text-[10px] font-medium uppercase tracking-wider text-muted">
                Active links
              </div>
              <ul className="flex flex-col gap-2">
                {links.map((l) => (
                  <li
                    key={l.token}
                    className="flex items-center justify-between gap-2 rounded-lg border border-border-subtle bg-surface px-3 py-2 text-[12px]"
                  >
                    <div className="flex min-w-0 flex-col">
                      <span className="truncate font-mono text-foreground">{l.url}</span>
                      <span className="text-[10px] text-muted">
                        {l.permission} ·{" "}
                        {l.expires_at ? `expires ${new Date(l.expires_at).toLocaleDateString()}` : "no expiry"}
                        {" · "}
                        {l.view_count} view{l.view_count === 1 ? "" : "s"}
                      </span>
                    </div>
                    <div className="flex items-center gap-2">
                      <button
                        onClick={async () => {
                          await navigator.clipboard.writeText(l.url);
                          setCopiedId(l.token);
                          setTimeout(() => setCopiedId(null), 1200);
                        }}
                        className="rounded-md border border-border-subtle px-2 py-1 hover:border-brand hover:text-brand"
                      >
                        {copiedId === l.token ? "Copied" : "Copy"}
                      </button>
                      <button
                        onClick={() => revoke(l.token)}
                        className="text-muted hover:text-red-400"
                      >
                        Revoke
                      </button>
                    </div>
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
