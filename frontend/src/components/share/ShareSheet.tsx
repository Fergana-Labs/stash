"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import {
  ObjectPermissions,
  ObjectShare,
  ObjectVisibility,
  ShareableObjectType,
  addObjectShare,
  createShareLink,
  getObjectPermissions,
  removeObjectShare,
  setObjectVisibility,
} from "../../lib/api";

interface UserResult {
  id: string;
  name: string;
  display_name: string;
}

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:3456";

interface Props {
  objectType: ShareableObjectType;
  objectId: string;
  objectLabel: string;
  onClose: () => void;
  // When provided, the sheet renders fixed-positioned at the given viewport
  // coords (used by the wiki tree right-click flow). Otherwise it anchors
  // inline relative to its `relative` parent.
  anchorAt?: { x: number; y: number } | null;
}

const VISIBILITY_OPTIONS: { value: ObjectVisibility; label: string; hint: string }[] = [
  { value: "private", label: "Restricted", hint: "Only people you've added can open" },
  { value: "link", label: "Anyone with the link", hint: "Anyone with the URL can read" },
  { value: "public", label: "Public on the web", hint: "Discoverable in /discover" },
];

const TYPE_CHIPS: Partial<Record<ShareableObjectType, string>> = {
  page: "Page",
  folder: "Folder",
  table: "Table",
  workspace: "Workspace",
  file: "File",
  history: "Session",
  view: "View",
};

export default function ShareSheet({ objectType, objectId, objectLabel, onClose, anchorAt }: Props) {
  const containerRef = useRef<HTMLDivElement>(null);
  const [perms, setPerms] = useState<ObjectPermissions | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [updatingVis, setUpdatingVis] = useState(false);
  const [linkUrl, setLinkUrl] = useState<string | null>(null);
  const [embedSlug, setEmbedSlug] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);
  const [embedCopied, setEmbedCopied] = useState(false);

  const reload = useCallback(async () => {
    try {
      const p = await getObjectPermissions(objectType, objectId);
      setPerms(p);
      setLoadError(null);
    } catch (err) {
      setLoadError(err instanceof Error ? err.message : "Failed to load permissions");
    }
  }, [objectType, objectId]);

  useEffect(() => {
    reload();
  }, [reload]);

  useEffect(() => {
    const onDown = (e: MouseEvent) => {
      if (!containerRef.current) return;
      if (!containerRef.current.contains(e.target as Node)) onClose();
    };
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    document.addEventListener("mousedown", onDown);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onDown);
      document.removeEventListener("keydown", onKey);
    };
  }, [onClose]);

  const currentVisibility: ObjectVisibility = perms?.visibility ?? "inherit";
  // 'inherit' isn't user-facing in this dropdown — display it as Restricted because
  // workspace members can already see it via their membership.
  const dropdownValue: ObjectVisibility = currentVisibility === "inherit" ? "private" : currentVisibility;

  const onChangeVisibility = async (next: ObjectVisibility) => {
    if (next === dropdownValue) return;
    setUpdatingVis(true);
    try {
      await setObjectVisibility(objectType, objectId, next);
      await reload();
    } catch (err) {
      setLoadError(err instanceof Error ? err.message : "Failed to update visibility");
    } finally {
      setUpdatingVis(false);
    }
  };

  const onCopyLink = async () => {
    let result;
    try {
      result = await createShareLink(objectType, objectId, "link");
    } catch (err) {
      setLoadError(err instanceof Error ? err.message : "Failed to create link");
      return;
    }
    setLinkUrl(result.url);
    setEmbedSlug(result.kind === "view" ? result.view_slug ?? null : null);
    await reload();
    // Clipboard is best-effort — some browsers (headless, sandboxed iframes,
    // permission denied) reject writeText. The URL is still shown above so
    // the user can select-and-copy by hand.
    try {
      await navigator.clipboard.writeText(result.url);
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch {
      /* ignore — link is rendered for manual copy */
    }
  };

  const onCopyEmbed = async () => {
    if (!embedSlug) return;
    const origin = window.location.origin;
    const snippet = `<iframe src="${origin}/v/${embedSlug}/embed" width="100%" height="600" frameborder="0"></iframe>`;
    try {
      await navigator.clipboard.writeText(snippet);
      setEmbedCopied(true);
      setTimeout(() => setEmbedCopied(false), 1500);
    } catch {
      /* ignore — snippet is rendered for manual copy */
    }
  };

  const containerClass = anchorAt
    ? "fixed z-30 w-[360px] rounded-lg border border-border bg-surface shadow-xl"
    : "absolute right-0 top-9 z-30 w-[360px] rounded-lg border border-border bg-surface shadow-xl";
  const containerStyle = anchorAt
    ? { left: Math.min(anchorAt.x, window.innerWidth - 376), top: anchorAt.y + 4 }
    : undefined;
  const typeChip = TYPE_CHIPS[objectType];

  return (
    <div ref={containerRef} className={containerClass} style={containerStyle}>
      <div className="border-b border-border-subtle px-4 py-3">
        <div className="flex items-center gap-2">
          <span className="text-[13px] font-medium text-foreground">Share</span>
          {typeChip && (
            <span className="rounded border border-border-subtle bg-raised px-1.5 py-0.5 font-mono text-[10px] uppercase tracking-[0.08em] text-muted">
              {typeChip}
            </span>
          )}
        </div>
        <div className="truncate text-[12px] text-muted">{objectLabel}</div>
      </div>

      {loadError && (
        <div className="border-b border-border-subtle bg-red-500/5 px-4 py-2 text-[12px] text-red-500">
          {loadError}
        </div>
      )}

      {perms && (
        <>
          <PeopleSection
            objectType={objectType}
            objectId={objectId}
            shares={perms.shares}
            onChange={reload}
          />

          <div className="border-t border-border-subtle px-4 py-3">
            <div className="mb-2 font-mono text-[11px] uppercase tracking-wider text-muted">
              General access
            </div>
            <select
              value={dropdownValue}
              onChange={(e) => onChangeVisibility(e.target.value as ObjectVisibility)}
              disabled={updatingVis}
              className="w-full rounded border border-border bg-raised px-2 py-1.5 text-[13px] text-foreground"
            >
              {VISIBILITY_OPTIONS.map((opt) => (
                <option key={opt.value} value={opt.value}>
                  {opt.label}
                </option>
              ))}
            </select>
            <div className="mt-1.5 text-[11px] text-muted">
              {VISIBILITY_OPTIONS.find((o) => o.value === dropdownValue)?.hint}
            </div>
          </div>

          <div className="flex items-center justify-between gap-2 border-t border-border-subtle px-4 py-3">
            <div className="min-w-0 flex-1 truncate text-[12px] text-dim">
              {linkUrl ?? "Get a shareable link"}
            </div>
            <button
              onClick={onCopyLink}
              className={
                "shrink-0 rounded border px-3 py-1 text-[12px] " +
                (copied
                  ? "border-brand/40 bg-brand/15 text-brand"
                  : "border-border bg-raised text-foreground hover:border-foreground")
              }
            >
              {copied ? "Copied!" : "Copy link"}
            </button>
          </div>

          {embedSlug && (
            <div className="flex items-center justify-between gap-2 border-t border-border-subtle px-4 py-3">
              <div className="min-w-0 flex-1 truncate font-mono text-[11px] text-dim">
                &lt;iframe src=&quot;…/v/{embedSlug}/embed&quot;&gt;
              </div>
              <button
                onClick={onCopyEmbed}
                className={
                  "shrink-0 rounded border px-3 py-1 text-[12px] " +
                  (embedCopied
                    ? "border-brand/40 bg-brand/15 text-brand"
                    : "border-border bg-raised text-foreground hover:border-foreground")
                }
              >
                {embedCopied ? "Copied!" : "Copy embed"}
              </button>
            </div>
          )}
        </>
      )}
    </div>
  );
}

function PeopleSection({
  objectType,
  objectId,
  shares,
  onChange,
}: {
  objectType: ShareableObjectType;
  objectId: string;
  shares: ObjectShare[];
  onChange: () => void | Promise<void>;
}) {
  return (
    <div className="px-4 py-3">
      <div className="mb-2 font-mono text-[11px] uppercase tracking-wider text-muted">
        People with access
      </div>
      <div className="space-y-1.5">
        {shares.length === 0 && (
          <div className="text-[12px] text-muted">No one shared yet — workspace members already have access.</div>
        )}
        {shares.map((s) => (
          <ShareRow
            key={s.user_id}
            share={s}
            onRemove={async () => {
              await removeObjectShare(objectType, objectId, s.user_id);
              await onChange();
            }}
          />
        ))}
      </div>
      <AddPersonInput
        onAdd={async (userId, permission) => {
          await addObjectShare(objectType, objectId, userId, permission);
          await onChange();
        }}
        excludeUserIds={shares.map((s) => s.user_id)}
      />
    </div>
  );
}

function ShareRow({ share, onRemove }: { share: ObjectShare; onRemove: () => Promise<void> }) {
  const [removing, setRemoving] = useState(false);
  return (
    <div className="flex items-center justify-between gap-2 rounded bg-raised px-2 py-1.5 text-[12px]">
      <span className="truncate text-foreground">{share.user_name || share.user_id.slice(0, 8)}</span>
      <span className="font-mono text-[10px] uppercase tracking-wider text-muted">{share.permission}</span>
      <button
        onClick={async () => {
          setRemoving(true);
          try {
            await onRemove();
          } finally {
            setRemoving(false);
          }
        }}
        disabled={removing}
        className="text-[11px] text-muted hover:text-red-500 disabled:opacity-50"
      >
        ×
      </button>
    </div>
  );
}

function AddPersonInput({
  onAdd,
  excludeUserIds,
}: {
  onAdd: (userId: string, permission: "read" | "write") => Promise<void>;
  excludeUserIds: string[];
}) {
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<UserResult[]>([]);
  const [permission, setPermission] = useState<"read" | "write">("read");
  const [adding, setAdding] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const exclude = useMemo(() => new Set(excludeUserIds), [excludeUserIds]);

  const search = useCallback(
    async (q: string) => {
      if (q.length < 1) {
        setResults([]);
        return;
      }
      try {
        const token = localStorage.getItem("stash_token") || "";
        const res = await fetch(`${API_BASE}/api/v1/users/search?q=${encodeURIComponent(q)}`, {
          headers: { Authorization: `Bearer ${token}` },
        });
        if (res.ok) {
          const data: UserResult[] = await res.json();
          setResults(data.filter((u) => !exclude.has(u.id)));
        }
      } catch {
        // search failures are non-fatal
      }
    },
    [exclude]
  );

  const handleInput = (v: string) => {
    setQuery(v);
    setError(null);
    if (debounceRef.current) clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(() => search(v), 200);
  };

  const handlePick = async (u: UserResult) => {
    setAdding(true);
    setError(null);
    try {
      await onAdd(u.id, permission);
      setQuery("");
      setResults([]);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to add");
    } finally {
      setAdding(false);
    }
  };

  return (
    <div className="mt-2">
      <div className="flex items-center gap-1.5">
        <input
          type="text"
          value={query}
          onChange={(e) => handleInput(e.target.value)}
          placeholder="Add person by username"
          disabled={adding}
          className="min-w-0 flex-1 rounded border border-border bg-raised px-2 py-1 text-[12px] text-foreground placeholder:text-muted"
        />
        <select
          value={permission}
          onChange={(e) => setPermission(e.target.value as "read" | "write")}
          className="shrink-0 rounded border border-border bg-raised px-1.5 py-1 text-[11px] text-foreground"
        >
          <option value="read">Viewer</option>
          <option value="write">Editor</option>
        </select>
      </div>
      {error && <div className="mt-1 text-[11px] text-red-500">{error}</div>}
      {results.length > 0 && (
        <div className="mt-1 max-h-40 overflow-y-auto rounded border border-border-subtle bg-surface">
          {results.map((u) => (
            <button
              key={u.id}
              onClick={() => handlePick(u)}
              disabled={adding}
              className="flex w-full items-center justify-between gap-2 px-2 py-1.5 text-left text-[12px] text-foreground hover:bg-raised disabled:opacity-50"
            >
              <span className="truncate">{u.display_name || u.name}</span>
              <span className="text-[11px] text-muted">@{u.name}</span>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
