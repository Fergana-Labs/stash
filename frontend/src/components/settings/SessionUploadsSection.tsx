"use client";

import { useState } from "react";
import { updateMe } from "../../lib/api";
import type { User } from "../../lib/types";

// The master consent switch (Multiplier). Off = the backend rejects new
// session uploads outright, so agents surface the refusal instead of
// streaming into a void.
export default function SessionUploadsSection({
  user,
  onUpdated,
}: {
  user: User;
  onUpdated: () => void;
}) {
  const enabled = user.session_uploads_enabled !== false;
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  async function toggle() {
    setSaving(true);
    setError("");
    try {
      await updateMe({ session_uploads_enabled: !enabled });
      onUpdated();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Update failed");
    } finally {
      setSaving(false);
    }
  }

  return (
    <section className="rounded-2xl border border-border bg-surface p-6 space-y-4">
      <div className="flex items-start justify-between gap-4">
        <div>
          <h2 className="text-base font-semibold text-foreground">Session uploads</h2>
          <p className="text-xs text-muted-foreground mt-0.5">
            {enabled
              ? "Your agents' session transcripts are uploaded to your private stash. " +
                "Raw transcripts stay private; distilled learnings feed your team's " +
                "wiki and skills unless you exclude a session."
              : "Uploads are off: agents attempting to push transcripts get an " +
                "explicit error. Existing sessions are untouched."}
          </p>
        </div>
        <button
          type="button"
          role="switch"
          aria-checked={enabled}
          onClick={toggle}
          disabled={saving}
          className={`cursor-pointer relative inline-flex h-6 w-11 shrink-0 items-center rounded-full transition-colors disabled:opacity-60 ${
            enabled ? "bg-brand" : "bg-border"
          }`}
        >
          <span
            className={`inline-block h-4 w-4 transform rounded-full bg-white transition-transform ${
              enabled ? "translate-x-6" : "translate-x-1"
            }`}
          />
        </button>
      </div>
      {error && <p className="text-xs text-error">{error}</p>}
    </section>
  );
}
