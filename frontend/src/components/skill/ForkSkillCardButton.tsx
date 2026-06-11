"use client";

import { useRouter } from "next/navigation";
import { useEffect, useMemo, useRef, useState } from "react";

import {
  forkSkill,
  ApiError,
  getToken,
  listMyWorkspaces,
} from "../../lib/api";
import type { Workspace } from "../../lib/types";

type Props = {
  slug: string;
  sourceWorkspaceId: string;
};

type Phase =
  | { kind: "idle" }
  | { kind: "loading" }
  | { kind: "picking"; workspaces: Workspace[]; selectedId: string }
  | { kind: "saving" }
  | { kind: "done"; workspaceId: string }
  | { kind: "error"; message: string };

// Compact corner-overlay variant of AddToWorkspaceButton, designed to sit
// on top of a SkillCard. Click is swallowed so the parent <Link> doesn't
// navigate to the skill detail page.
export default function ForkSkillCardButton({ slug, sourceWorkspaceId }: Props) {
  const router = useRouter();
  const [phase, setPhase] = useState<Phase>({ kind: "idle" });
  const popoverRef = useRef<HTMLDivElement>(null);
  const popoverOpen =
    phase.kind === "picking" ||
    phase.kind === "saving" ||
    phase.kind === "done" ||
    phase.kind === "error";

  // Close the popover when the user clicks outside it. The button-click
  // already stops propagation, so this only fires for genuine outside
  // clicks (including elsewhere on the card).
  useEffect(() => {
    if (!popoverOpen) return;
    function onDocClick(e: MouseEvent) {
      if (!popoverRef.current) return;
      if (popoverRef.current.contains(e.target as Node)) return;
      setPhase({ kind: "idle" });
    }
    document.addEventListener("mousedown", onDocClick);
    return () => document.removeEventListener("mousedown", onDocClick);
  }, [popoverOpen]);

  const eligible = useMemo(() => {
    if (phase.kind !== "picking") return [];
    return phase.workspaces.filter((w) => w.id !== sourceWorkspaceId);
  }, [phase, sourceWorkspaceId]);

  async function openPicker() {
    if (!getToken()) {
      router.push(`/login?next=${encodeURIComponent(`/skills/${slug}?action=add`)}`);
      return;
    }
    setPhase({ kind: "loading" });
    try {
      const data = await listMyWorkspaces();
      const usable = data.workspaces.filter((w) => w.id !== sourceWorkspaceId);
      if (usable.length === 0) {
        setPhase({ kind: "error", message: "No other workspace available." });
        return;
      }
      // One-click path: if there's only one eligible workspace, add immediately.
      if (usable.length === 1) {
        await save(usable[0].id);
        return;
      }
      setPhase({
        kind: "picking",
        workspaces: data.workspaces,
        selectedId: usable[0].id,
      });
    } catch (e) {
      const message =
        e instanceof ApiError ? e.message : "Could not load workspaces";
      setPhase({ kind: "error", message });
    }
  }

  async function save(workspaceId: string) {
    setPhase({ kind: "saving" });
    try {
      await forkSkill(slug, workspaceId);
      setPhase({ kind: "done", workspaceId });
    } catch (e) {
      const message = e instanceof ApiError ? e.message : "Could not add skill";
      setPhase({ kind: "error", message });
    }
  }

  function onPrimaryClick(e: React.MouseEvent) {
    // Sit inside the card's <Link>; never let the click navigate.
    e.preventDefault();
    e.stopPropagation();
    if (phase.kind === "idle" || phase.kind === "error") void openPicker();
  }

  const showBusy = phase.kind === "loading" || phase.kind === "saving";
  const showDone = phase.kind === "done";

  return (
    <div
      className="relative"
      onClick={(e) => {
        // Any click inside the popover region (including the trigger) must
        // not bubble to the underlying card-link.
        e.preventDefault();
        e.stopPropagation();
      }}
    >
      <button
        type="button"
        onClick={onPrimaryClick}
        disabled={showBusy}
        title={showDone ? "Saved to workspace" : "Save to your workspace"}
        className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[11px] font-medium shadow-sm ring-1 backdrop-blur transition ${
          showDone
            ? "bg-[var(--color-brand-600)] text-white ring-[var(--color-brand-600)]"
            : "bg-white/85 text-foreground ring-border hover:bg-white"
        } disabled:cursor-wait`}
      >
        {showDone ? "✓ Saved" : showBusy ? "Saving…" : "+ Save"}
      </button>

      {popoverOpen && (
        <div
          ref={popoverRef}
          className="absolute right-0 top-7 z-30 w-[240px] rounded-lg border border-border bg-surface p-3 text-left text-foreground shadow-lg"
        >
          {phase.kind === "picking" && (
            <div className="space-y-2">
              <div className="sys-label" style={{ fontSize: 10.5 }}>
                Save to workspace
              </div>
              <select
                value={phase.selectedId}
                onChange={(e) =>
                  setPhase({ ...phase, selectedId: e.target.value })
                }
                className="w-full rounded-md border border-border bg-raised px-2 py-1.5 text-[12.5px] text-foreground focus:border-brand focus:outline-none"
              >
                {eligible.map((w) => (
                  <option key={w.id} value={w.id}>
                    {w.name}
                  </option>
                ))}
              </select>
              <button
                type="button"
                onClick={() => void save(phase.selectedId)}
                className="w-full rounded-md bg-brand px-2.5 py-1.5 text-[12.5px] font-medium text-white hover:bg-brand-hover"
              >
                Save
              </button>
            </div>
          )}
          {phase.kind === "saving" && (
            <div className="text-[12.5px] text-muted">Saving…</div>
          )}
          {phase.kind === "done" && (
            <div className="space-y-2">
              <div className="text-[12.5px] font-medium">
                Added to your workspace.
              </div>
              <button
                type="button"
                onClick={() =>
                  router.push(`/workspaces/${phase.workspaceId}`)
                }
                className="w-full rounded-md border border-border px-2.5 py-1.5 text-[12.5px] text-foreground hover:border-brand hover:text-brand"
              >
                Open workspace →
              </button>
            </div>
          )}
          {phase.kind === "error" && (
            <div className="text-[12px] text-red-500">{phase.message}</div>
          )}
        </div>
      )}
    </div>
  );
}
