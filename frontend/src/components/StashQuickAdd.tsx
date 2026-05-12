"use client";

import { useState, type FormEvent } from "react";
import { createWorkspaceHistoryEvent } from "../lib/api";
import type { User } from "../lib/types";

interface StashQuickAddProps {
  stashId: string;
  user: User;
}

type Status = "idle" | "saving" | "saved" | "error";

export default function StashQuickAdd({ stashId, user }: StashQuickAddProps) {
  const [value, setValue] = useState("");
  const [status, setStatus] = useState<Status>("idle");

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    const text = value.trim();
    if (!text || status === "saving") return;

    setStatus("saving");
    const title = text.split("\n")[0].slice(0, 80) || "Manual source";
    try {
      await createWorkspaceHistoryEvent(stashId, {
        agent_name: user.name || "user",
        event_type: "source",
        content: text === title ? text : `${title}\n\n${text}`,
        session_id: `manual-source-${Date.now()}`,
        metadata: {
          source: "manual_ui",
          title,
          added_by: user.display_name || user.name,
        },
      });
    } catch {
      setStatus("error");
      window.setTimeout(() => setStatus("idle"), 2500);
      return;
    }
    setValue("");
    setStatus("saved");
    window.setTimeout(() => setStatus("idle"), 1500);
  }

  return (
    <form
      onSubmit={handleSubmit}
      className="flex items-center gap-2 border-b border-border bg-surface/40 px-3 py-1.5"
    >
      <span className="flex h-5 w-5 flex-shrink-0 items-center justify-center rounded bg-[var(--color-brand-500)] text-[13px] font-semibold leading-none text-white">
        +
      </span>
      <input
        type="text"
        value={value}
        onChange={(e) => setValue(e.target.value)}
        placeholder="Add to stash — paste a link or type a note, press Enter"
        disabled={status === "saving"}
        className="h-7 flex-1 bg-transparent text-[13px] text-foreground outline-none placeholder:text-muted disabled:opacity-60"
      />
      {value.trim() && (
        <button
          type="submit"
          disabled={status === "saving"}
          className="rounded-md bg-[var(--color-brand-600)] px-2.5 py-1 text-[12px] font-medium text-white hover:bg-[var(--color-brand-700)] disabled:opacity-60"
        >
          {status === "saving" ? "Adding…" : "Add"}
        </button>
      )}
      {status === "saved" && (
        <span className="text-[11.5px] font-medium text-[var(--color-brand-700)]">Added</span>
      )}
      {status === "error" && (
        <span className="text-[11.5px] font-medium text-red-500">Failed</span>
      )}
    </form>
  );
}
