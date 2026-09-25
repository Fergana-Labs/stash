"use client";

import { ThumbsDown, ThumbsUp } from "lucide-react";
import { useState } from "react";
import { rateSession, type SessionRating as Rating } from "@/lib/api";
import { cn } from "@/lib/utils";

/** The user's good/bad verdict on a session. Clicking the active verdict
 *  clears it. */
export default function SessionRating({
  sessionId,
  rating,
  onChange,
}: {
  sessionId: string;
  rating: Rating | null;
  onChange: (rating: Rating | null) => void;
}) {
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function rate(next: Rating) {
    const value = rating === next ? null : next;
    setSaving(true);
    setError(null);
    try {
      const saved = await rateSession(sessionId, value);
      onChange(saved.rating);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Could not save rating");
    } finally {
      setSaving(false);
    }
  }

  return (
    <span className="inline-flex items-center gap-1">
      <RatingButton
        label="Good session"
        active={rating === "good"}
        disabled={saving}
        onClick={() => void rate("good")}
        activeClass="text-emerald-600 bg-emerald-500/10"
      >
        <ThumbsUp className="h-3.5 w-3.5" />
      </RatingButton>
      <RatingButton
        label="Bad session"
        active={rating === "bad"}
        disabled={saving}
        onClick={() => void rate("bad")}
        activeClass="text-rose-600 bg-rose-500/10"
      >
        <ThumbsDown className="h-3.5 w-3.5" />
      </RatingButton>
      {error && <span className="text-[11px] text-error">{error}</span>}
    </span>
  );
}

function RatingButton({
  label,
  active,
  disabled,
  onClick,
  activeClass,
  children,
}: {
  label: string;
  active: boolean;
  disabled: boolean;
  onClick: () => void;
  activeClass: string;
  children: React.ReactNode;
}) {
  return (
    <button
      type="button"
      aria-label={label}
      aria-pressed={active}
      title={label}
      disabled={disabled}
      onClick={onClick}
      className={cn(
        "cursor-pointer rounded-md p-1 transition-colors disabled:opacity-50",
        active ? activeClass : "text-muted-foreground hover:bg-raised hover:text-foreground",
      )}
    >
      {children}
    </button>
  );
}
