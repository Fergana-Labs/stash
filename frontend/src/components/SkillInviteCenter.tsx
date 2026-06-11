"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import {
  dismissSkillInvite,
  listSkillInvites,
  type SkillInvite,
} from "../lib/api";
import { SkeletonBlock } from "./SkeletonStates";
import { NotificationsIcon } from "./SkillIcons";

export default function SkillInviteCenter() {
  const router = useRouter();
  const containerRef = useRef<HTMLDivElement>(null);
  const [open, setOpen] = useState(false);
  const [invites, setInvites] = useState<SkillInvite[]>([]);
  const [loading, setLoading] = useState(false);
  const [busyInviteId, setBusyInviteId] = useState<string | null>(null);
  const [error, setError] = useState("");

  const loadInvites = useCallback(async () => {
    try {
      setInvites(await listSkillInvites());
    } catch {
      setInvites([]);
    }
  }, []);

  const loadPanel = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      setInvites(await listSkillInvites());
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load Skill invites");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadInvites();
  }, [loadInvites]);

  useEffect(() => {
    if (!open) return;
    void loadPanel();
  }, [loadPanel, open]);

  useEffect(() => {
    if (!open) return;

    function onMouseDown(event: MouseEvent) {
      if (!containerRef.current?.contains(event.target as Node)) setOpen(false);
    }

    function onKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") setOpen(false);
    }

    document.addEventListener("mousedown", onMouseDown);
    document.addEventListener("keydown", onKeyDown);
    return () => {
      document.removeEventListener("mousedown", onMouseDown);
      document.removeEventListener("keydown", onKeyDown);
    };
  }, [open]);

  function view(invite: SkillInvite) {
    setOpen(false);
    router.push(`/skills/${invite.skill_slug}`);
  }

  async function dismiss(invite: SkillInvite) {
    setBusyInviteId(invite.id);
    setError("");
    try {
      await dismissSkillInvite(invite.id);
      setInvites((current) => current.filter((item) => item.id !== invite.id));
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to dismiss invite");
    } finally {
      setBusyInviteId(null);
    }
  }

  return (
    <div ref={containerRef} className="relative">
      <button
        type="button"
        onClick={() => setOpen((value) => !value)}
        className="relative rounded p-1 text-muted hover:bg-raised hover:text-foreground"
        aria-label={`Skill access${invites.length ? ` (${invites.length})` : ""}`}
        title="Skill access"
      >
        <NotificationsIcon className="h-4 w-4" />
        {invites.length > 0 ? (
          <span className="absolute -right-0.5 -top-0.5 inline-flex min-w-4 items-center justify-center rounded-full bg-[var(--color-brand-600)] px-1 text-[10px] font-semibold leading-4 text-white">
            {invites.length}
          </span>
        ) : null}
      </button>

      {open ? (
        <div className="absolute right-0 top-8 z-50 w-[360px] rounded-lg border border-border bg-base shadow-xl">
          <div className="flex items-center justify-between border-b border-border px-4 py-3">
            <div>
              <h2 className="text-[14px] font-semibold text-foreground">Skill access</h2>
              <p className="mt-0.5 text-[11.5px] text-muted">
                Review Skills shared directly with you.
              </p>
            </div>
            <button
              type="button"
              onClick={() => void loadPanel()}
              className="rounded-md border border-border-subtle px-2 py-1 text-[11px] text-muted hover:text-foreground"
            >
              Refresh
            </button>
          </div>

          <div className="max-h-[460px] overflow-y-auto p-3">
            {error ? (
              <div className="mb-2 rounded-md border border-red-300/40 bg-red-500/10 px-3 py-2 text-[12px] text-red-500">
                {error}
              </div>
            ) : null}

            {loading ? (
              <div className="space-y-2 px-1 py-1">
                {[0, 1, 2].map((row) => (
                  <div key={row} className="rounded-lg border border-border-subtle bg-surface p-3">
                    <SkeletonBlock className="h-4 w-44" />
                    <SkeletonBlock className="mt-2 h-3 w-full" />
                    <SkeletonBlock className="mt-3 h-7 w-24" />
                  </div>
                ))}
              </div>
            ) : invites.length === 0 ? (
              <p className="px-2 py-8 text-center text-[12.5px] text-muted">
                No new skill access.
              </p>
            ) : (
              <div className="flex flex-col gap-2">
                {invites.map((invite) => {
                  const inviter = invite.invited_by_display_name;
                  const busy = busyInviteId === invite.id;

                  return (
                    <div key={invite.id} className="rounded-lg border border-border-subtle bg-surface p-3">
                      <div className="min-w-0">
                        <h3 className="truncate text-[13px] font-semibold text-foreground">
                          {invite.skill_title}
                        </h3>
                        <p className="mt-1 line-clamp-2 text-[12px] leading-relaxed text-muted">
                          {invite.skill_description || "No description."}
                        </p>
                        <p className="mt-2 text-[11px] text-muted">
                          {inviter} has given you view access to their skill.
                        </p>
                        <p className="mt-1 text-[11px] text-muted">
                          From {invite.source_workspace_name}
                        </p>
                      </div>

                      <div className="mt-3 flex justify-end gap-1.5">
                        <button
                          type="button"
                          disabled={busy}
                          onClick={() => void dismiss(invite)}
                          className="rounded-md border border-border-subtle px-2.5 py-1.5 text-[12px] text-muted hover:text-foreground disabled:opacity-50"
                        >
                          Dismiss
                        </button>
                        <button
                          type="button"
                          disabled={busy}
                          onClick={() => view(invite)}
                          className="rounded-md bg-[var(--color-brand-600)] px-2.5 py-1.5 text-[12px] font-medium text-white hover:bg-[var(--color-brand-700)] disabled:opacity-50"
                        >
                          View Skill
                        </button>
                      </div>
                    </div>
                  );
                })}
              </div>
            )}
          </div>
        </div>
      ) : null}
    </div>
  );
}
