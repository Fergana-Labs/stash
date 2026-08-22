"use client";

import { useState } from "react";

import { updateUser } from "@/lib/api";
import type { EndUser } from "@/lib/types";
import { cn } from "@/lib/utils";

/** Whether this user's sessions feed the shared anonymized wiki. A real switch
 *  (track and knob), not a pill — it must read as clickable at a glance.
 *  Shared by the user list and the user detail page so the control behaves
 *  identically in both. */
export default function WikiToggle({ user, onChanged }: { user: EndUser; onChanged: () => void }) {
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function toggle() {
    setSaving(true);
    setError(null);
    try {
      await updateUser(user.id, { share_wiki: !user.share_wiki });
      onChanged();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not change the wiki setting");
    } finally {
      setSaving(false);
    }
  }

  return (
    <span className="shrink-0">
      <button
        role="switch"
        aria-checked={user.share_wiki}
        onClick={(e) => {
          // The row around this is a link to the user.
          e.preventDefault();
          e.stopPropagation();
          void toggle();
        }}
        disabled={saving}
        title="Whether this user's sessions feed the shared anonymized memory"
        className="group flex cursor-pointer items-center gap-2 disabled:opacity-50"
      >
        <span
          className={cn(
            "relative h-5 w-9 rounded-full transition-colors",
            user.share_wiki ? "bg-brand-500" : "bg-border group-hover:bg-muted-foreground/40",
          )}
        >
          <span
            className={cn(
              "absolute top-0.5 h-4 w-4 rounded-full bg-white shadow-sm transition-[left]",
              user.share_wiki ? "left-[18px]" : "left-0.5",
            )}
          />
        </span>
        <span
          className={cn(
            "text-[13px]",
            user.share_wiki ? "font-medium text-brand-500" : "text-muted-foreground",
          )}
        >
          {user.share_wiki ? "Feeds shared memory" : "Opted out"}
        </span>
      </button>
      {error && <span className="mt-1 block text-[12px] text-error">{error}</span>}
    </span>
  );
}
