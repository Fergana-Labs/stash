"use client";

import { useEffect, useRef, useState } from "react";
import { useEscapeKey } from "../../hooks/useEscapeKey";
import {
  listObjectShares,
  setGeneralAccess,
  updateSkill,
  type GeneralAccess,
  type SkillRecord,
  type SkillRecordInfo,
} from "../../lib/api";
import { resetSkillNavigationCache } from "../../lib/skillNavigationCache";
import { ACCESS_COLOR } from "./SkillCard";

type HandoffStatus = "idle" | "copying" | "copied" | "error";

function recordInfo(record: SkillRecord): SkillRecordInfo {
  return {
    id: record.id,
    slug: record.slug,
    title: record.title,
    discoverable: record.discoverable,
    cover_image_url: record.cover_image_url,
    icon_url: record.icon_url,
    view_count: record.view_count,
  };
}

// Public-link controls for a skill folder. The skill record (slug) always
// exists; publicity is a general-access share on the folder. The popover
// toggles Restricted / Anyone with the link, exposes the public URL, and
// manages the Discover listing. Person-to-person sharing is the folder's
// generic ResourceShareButton, rendered next to this one.
export default function SkillShareButton({
  folderId,
  skill: skillProp,
  onSkillChange,
}: {
  folderId: string;
  skill: SkillRecordInfo;
  onSkillChange?: (skill: SkillRecordInfo) => void;
}) {
  const [skill, setSkill] = useState<SkillRecordInfo>(skillProp);
  const [access, setAccess] = useState<GeneralAccess | null>(null);
  const [open, setOpen] = useState(false);
  const [copied, setCopied] = useState(false);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const [handoffStatus, setHandoffStatus] = useState<HandoffStatus>("idle");
  const [handoffMessage, setHandoffMessage] = useState("");
  const popoverRef = useRef<HTMLDivElement>(null);

  useEscapeKey(open, () => setOpen(false));

  useEffect(() => {
    setSkill(skillProp);
  }, [skillProp]);

  useEffect(() => {
    let cancelled = false;
    listObjectShares("folder", folderId)
      .then((res) => {
        if (!cancelled) setAccess(res.general_access);
      })
      .catch((e) => {
        if (!cancelled) {
          setMessage(e instanceof Error ? e.message : "Could not load access.");
        }
      });
    return () => {
      cancelled = true;
    };
  }, [folderId]);

  const isPublic = access === "public";

  function applySkill(next: SkillRecordInfo) {
    setSkill(next);
    onSkillChange?.(next);
    resetSkillNavigationCache();
  }

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

  async function changeAccess(next: GeneralAccess) {
    setBusy(true);
    setMessage("");
    try {
      await setGeneralAccess("folder", folderId, next);
      setAccess(next);
      resetSkillNavigationCache();
    } catch (e) {
      setMessage(e instanceof Error ? e.message : "Could not update access.");
    } finally {
      setBusy(false);
    }
  }

  async function copyLink() {
    try {
      await navigator.clipboard.writeText(absoluteUrl(`/skills/${skill.slug}`));
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

  async function toggleDiscoverable(nextDiscoverable: boolean) {
    setBusy(true);
    setMessage("");
    try {
      const updated = await updateSkill(skill.id, { discoverable: nextDiscoverable });
      applySkill(recordInfo(updated));
    } catch (e) {
      setMessage(e instanceof Error ? e.message : "Could not update Discover.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div ref={popoverRef} className="relative flex items-center gap-1.5">
      <button
        type="button"
        onClick={() => void copyAgentHandoffLink()}
        disabled={!isPublic || handoffStatus === "copying"}
        aria-label="Copy agent handoff link"
        title={
          isPublic
            ? "Copy an agent-readable public link"
            : "Make the skill public to copy an agent link"
        }
        className="inline-flex min-w-[72px] cursor-pointer items-center justify-center rounded-md bg-surface px-2.5 py-1 text-[12.5px] font-medium text-dim ring-1 ring-inset ring-border hover:bg-raised hover:text-foreground disabled:cursor-default disabled:opacity-50"
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
        className="inline-flex cursor-pointer items-center gap-1.5 rounded-md bg-[var(--color-brand-600)] px-2.5 py-1 text-[12.5px] font-medium text-white hover:bg-[var(--color-brand-700)]"
      >
        <span
          className="inline-block h-[7px] w-[7px] rounded-full"
          style={{ background: isPublic ? ACCESS_COLOR.public : ACCESS_COLOR.private }}
        />
        Public link
      </button>
      {(handoffMessage || (message && !open)) && (
        <div className="absolute right-0 top-full z-40 mt-1.5 max-w-[280px] rounded-md border border-border bg-base px-2 py-1.5 text-[12px] text-muted-foreground shadow-lg">
          {handoffMessage || message}
        </div>
      )}
      {open && (
        <div
          role="dialog"
          aria-label="Share skill"
          className="absolute right-0 top-full z-40 mt-1.5 w-[360px] rounded-lg border border-border bg-base p-3 shadow-lg"
        >
          <div className="sys-label mb-1">General access</div>
          <select
            value={access ?? "restricted"}
            disabled={busy || access === null}
            onChange={(e) => void changeAccess(e.target.value as GeneralAccess)}
            aria-label="General access"
            className="w-full rounded-md border border-border bg-surface px-2 py-1.5 text-[12.5px] text-foreground disabled:opacity-45"
          >
            <option value="restricted">Restricted</option>
            <option value="public">Anyone with the link can view</option>
          </select>

          {isPublic && (
            <>
              <div className="sys-label mb-1 mt-3">Public URL</div>
              <div className="flex gap-1.5">
                <input
                  readOnly
                  value={absoluteUrl(`/skills/${skill.slug}`)}
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
            </>
          )}

          <label className="mt-3 flex cursor-pointer items-center gap-2 rounded-md border border-border bg-surface px-2 py-1.5">
            <input
              type="checkbox"
              checked={skill.discoverable}
              disabled={busy || !isPublic}
              onChange={(e) => void toggleDiscoverable(e.target.checked)}
            />
            <span className="text-[12px] text-foreground">List on Discover</span>
          </label>
          {!isPublic && (
            <p className="mt-1.5 text-[11.5px] text-muted-foreground">
              Make the skill public to list it on Discover.
            </p>
          )}

          <div className="mt-3 text-[11.5px] text-muted-foreground">
            {skill.view_count} view{skill.view_count === 1 ? "" : "s"}
          </div>

          {message && <div className="mt-2 text-[12px] text-muted-foreground">{message}</div>}
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
