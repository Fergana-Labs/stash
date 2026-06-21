"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useEscapeKey } from "../../hooks/useEscapeKey";
import { useConfirm } from "../ConfirmDialog";
import {
  publishSkillFolder,
  unpublishSkill,
  updateSkill,
  type PublishedSkill,
  type SkillPublishInfo,
} from "../../lib/api";
import { resetSkillNavigationCache } from "../../lib/skillNavigationCache";

type HandoffStatus = "idle" | "copying" | "copied" | "error";

function publishInfoFromRecord(record: PublishedSkill): SkillPublishInfo {
  return {
    id: record.id,
    slug: record.slug,
    discoverable: record.discoverable,
    cover_image_url: record.cover_image_url,
    icon_url: record.icon_url,
    view_count: record.view_count,
  };
}

// Publish button for a skill folder. Published = publicly readable: the
// popover mints the publish record, then manages the public URL, the
// Discover listing, and unpublishing. Person-to-person sharing is the
// folder's generic ResourceShareButton, rendered next to this one.
export default function SkillShareButton({
  folderId,
  publish: publishProp,
  onPublishChange,
}: {
  folderId: string;
  publish: SkillPublishInfo | null;
  onPublishChange?: (publish: SkillPublishInfo | null) => void;
}) {
  const confirm = useConfirm();
  const [publish, setPublish] = useState<SkillPublishInfo | null>(publishProp);
  const [open, setOpen] = useState(false);
  const [copied, setCopied] = useState(false);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const [handoffStatus, setHandoffStatus] = useState<HandoffStatus>("idle");
  const [handoffMessage, setHandoffMessage] = useState("");
  const popoverRef = useRef<HTMLDivElement>(null);

  useEscapeKey(open, () => setOpen(false));

  useEffect(() => {
    setPublish(publishProp);
  }, [publishProp]);

  function applyPublish(next: SkillPublishInfo | null) {
    setPublish(next);
    onPublishChange?.(next);
    resetSkillNavigationCache();
  }

  const ensurePublished = useCallback(async (): Promise<SkillPublishInfo> => {
    if (publish) return publish;
    const record = await publishSkillFolder(folderId);
    const info = publishInfoFromRecord(record);
    setPublish(info);
    onPublishChange?.(info);
    resetSkillNavigationCache();
    return info;
  }, [publish, folderId, onPublishChange]);

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
    setMessage("");
    setCopied(false);
  }, [open]);

  async function publishNow() {
    setBusy(true);
    setMessage("");
    try {
      await ensurePublished();
    } catch (e) {
      setMessage(e instanceof Error ? e.message : "Could not publish skill.");
    } finally {
      setBusy(false);
    }
  }

  async function copyLink() {
    if (!publish) return;
    try {
      await navigator.clipboard.writeText(absoluteUrl(`/skills/${publish.slug}`));
      setCopied(true);
      setMessage("Link copied.");
      window.setTimeout(() => setCopied(false), 1600);
    } catch {
      setMessage("Failed to copy link.");
    }
  }

  async function copyAgentHandoffLink() {
    setOpen(false);
    setHandoffStatus("copying");
    setHandoffMessage("");
    try {
      const current = await ensurePublished();
      await navigator.clipboard.writeText(agentHandoffUrl(current.slug));
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

  async function toggleDiscoverable(nextDiscoverable: boolean) {
    if (!publish) return;
    setBusy(true);
    setMessage("");
    try {
      const updated = await updateSkill(publish.id, { discoverable: nextDiscoverable });
      applyPublish(publishInfoFromRecord(updated));
    } catch (e) {
      setMessage(e instanceof Error ? e.message : "Could not update Discover.");
    } finally {
      setBusy(false);
    }
  }

  async function unpublish() {
    if (!publish) return;
    const ok = await confirm({
      title: "Unpublish this skill?",
      body: "Its public link will stop working.",
      confirmLabel: "Unpublish",
    });
    if (!ok) return;

    setBusy(true);
    setMessage("");
    try {
      await unpublishSkill(publish.id);
      applyPublish(null);
      setOpen(false);
    } catch (e) {
      setMessage(e instanceof Error ? e.message : "Could not unpublish skill.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div ref={popoverRef} className="relative flex items-center gap-1.5">
      <button
        type="button"
        onClick={() => void copyAgentHandoffLink()}
        disabled={handoffStatus === "copying"}
        aria-label="Copy agent handoff link"
        title="Copy an agent-readable public link"
        className="inline-flex min-w-[72px] cursor-pointer items-center justify-center rounded-md bg-surface px-2.5 py-1 text-[12.5px] font-medium text-dim ring-1 ring-inset ring-border hover:bg-raised hover:text-foreground disabled:opacity-50"
      >
        {handoffStatus === "copying"
          ? "Copying"
          : handoffStatus === "copied"
            ? "Copied"
            : "Agent Handoff"}
      </button>
      <button
        type="button"
        onClick={() => setOpen((value) => !value)}
        aria-haspopup="dialog"
        aria-expanded={open}
        className="cursor-pointer rounded-md bg-[var(--color-brand-600)] px-2.5 py-1 text-[12.5px] font-medium text-white hover:bg-[var(--color-brand-700)]"
      >
        {publish ? "Published" : "Publish"}
      </button>
      {(handoffMessage || (message && !open)) && (
        <div className="absolute right-0 top-full z-40 mt-1.5 max-w-[280px] rounded-md border border-border bg-base px-2 py-1.5 text-[12px] text-muted shadow-lg">
          {handoffMessage || message}
        </div>
      )}
      {open && (
        <div
          role="dialog"
          aria-label="Publish skill"
          className="absolute right-0 top-full z-40 mt-1.5 w-[360px] rounded-lg border border-border bg-base p-3 shadow-lg"
        >
          {!publish ? (
            <>
              <p className="m-0 text-[12.5px] leading-relaxed text-muted">
                Publishing creates a public, read-only page for this skill.
                Anyone with the link can view it.
              </p>
              <button
                type="button"
                onClick={() => void publishNow()}
                disabled={busy}
                className="mt-3 w-full cursor-pointer rounded-md bg-[var(--color-brand-600)] px-2.5 py-1.5 text-[12.5px] font-medium text-white hover:bg-[var(--color-brand-700)] disabled:opacity-50"
              >
                {busy ? "Publishing..." : "Publish"}
              </button>
            </>
          ) : (
            <>
              <div className="sys-label mb-1">Public URL</div>
              <div className="flex gap-1.5">
                <input
                  readOnly
                  value={absoluteUrl(`/skills/${publish.slug}`)}
                  className="min-w-0 flex-1 rounded-md border border-border bg-surface px-2 py-1.5 text-[11.5px] font-mono text-foreground"
                />
                <button
                  type="button"
                  onClick={() => void copyLink()}
                  className="cursor-pointer rounded-md border border-border bg-base px-2 py-1.5 text-[11.5px] font-medium text-foreground hover:bg-raised"
                >
                  {copied ? "Copied" : "Copy"}
                </button>
              </div>

              <label className="mt-3 flex cursor-pointer items-center gap-2 rounded-md border border-border bg-surface px-2 py-1.5">
                <input
                  type="checkbox"
                  checked={publish.discoverable}
                  disabled={busy}
                  onChange={(e) => void toggleDiscoverable(e.target.checked)}
                />
                <span className="text-[12px] text-foreground">List on Discover</span>
              </label>

              <div className="mt-3 flex items-center justify-between gap-2">
                <span className="text-[11.5px] text-muted">
                  {publish.view_count} view{publish.view_count === 1 ? "" : "s"}
                </span>
                <button
                  type="button"
                  onClick={() => void unpublish()}
                  disabled={busy}
                  className="cursor-pointer text-[11.5px] font-medium text-red-500 hover:underline disabled:opacity-40"
                >
                  Unpublish
                </button>
              </div>
            </>
          )}

          {message && <div className="mt-2 text-[12px] text-muted">{message}</div>}
        </div>
      )}
    </div>
  );
}

function absoluteUrl(path: string): string {
  if (typeof window === "undefined") return path;
  return `${window.location.origin}${path}`;
}

function agentHandoffUrl(slug: string): string {
  return absoluteUrl(`/api/v1/skills/${slug}?format=text`);
}
