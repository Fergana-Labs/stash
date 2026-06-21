"use client";

import { useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";

import { forkSkill, ApiError } from "../../lib/api";

type Props = {
  slug: string;
};

type Phase =
  | { kind: "idle" }
  | { kind: "saving" }
  | { kind: "done"; folderId: string }
  | { kind: "error"; message: string };

// Compact corner-overlay save button, designed to sit on top of a SkillCard.
// Click is swallowed so the parent <Link> doesn't navigate to the skill
// detail page. Forking adds the skill to the current user's skills.
export default function ForkSkillCardButton({ slug }: Props) {
  const router = useRouter();
  const [phase, setPhase] = useState<Phase>({ kind: "idle" });
  const popoverRef = useRef<HTMLDivElement>(null);
  const popoverOpen = phase.kind === "done" || phase.kind === "error";

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

  function redirectToLogin() {
    router.push(`/login?next=${encodeURIComponent(`/skills/${slug}?action=add`)}`);
  }

  async function save() {
    setPhase({ kind: "saving" });
    try {
      const result = await forkSkill(slug);
      setPhase({ kind: "done", folderId: result.folder_id });
    } catch (e) {
      if (e instanceof ApiError && e.status === 401) {
        redirectToLogin();
        return;
      }
      const message = e instanceof ApiError ? e.message : "Could not add skill";
      setPhase({ kind: "error", message });
    }
  }

  function onPrimaryClick(e: React.MouseEvent) {
    // Sit inside the card's <Link>; never let the click navigate.
    e.preventDefault();
    e.stopPropagation();
    if (phase.kind === "idle" || phase.kind === "error") void save();
  }

  const showBusy = phase.kind === "saving";
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
        title={showDone ? "Saved to your skills" : "Save to your skills"}
        className={`inline-flex cursor-pointer items-center gap-1 rounded-full px-2 py-0.5 text-[11px] font-medium shadow-sm ring-1 backdrop-blur transition ${
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
          {phase.kind === "done" && (
            <div className="space-y-2">
              <div className="text-[12.5px] font-medium">
                Added to your skills.
              </div>
              <button
                type="button"
                onClick={() =>
                  router.push(`/skills/folder/${phase.folderId}`)
                }
                className="w-full cursor-pointer rounded-md border border-border px-2.5 py-1.5 text-[12.5px] text-foreground hover:border-brand hover:text-brand"
              >
                Open skill →
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
