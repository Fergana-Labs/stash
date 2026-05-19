"use client";

import { useState } from "react";

import {
  TaskStatus,
  importNotion,
  waitForTask,
} from "@/lib/integrations";

type Props = {
  workspaceId: string;
  folderId?: string | null;
  onDone?: (statuses: TaskStatus[]) => void;
  onClose: () => void;
};

/**
 * Modal form for Notion page imports. Accepts URLs OR bare page IDs,
 * one per line. The backend task normalizes either form. Requires the
 * user to have connected Notion in /settings/integrations AND shared
 * each page with the integration in Notion's UI — we surface a
 * helpful inline reminder rather than trying to bypass it.
 */
export default function NotionImportDialog({
  workspaceId,
  folderId,
  onDone,
  onClose,
}: Props) {
  const [raw, setRaw] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [statuses, setStatuses] = useState<TaskStatus[]>([]);
  const [error, setError] = useState<string | null>(null);

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    const urls = raw
      .split(/\s+/)
      .map((s) => s.trim())
      .filter(Boolean);
    if (urls.length === 0) {
      setError("Enter at least one Notion page or database URL.");
      return;
    }
    setSubmitting(true);
    setStatuses([]);
    try {
      const { task_ids } = await importNotion(workspaceId, {
        urls,
        folder_id: folderId || undefined,
      });
      const finals = await Promise.all(
        task_ids.map((tid) =>
          waitForTask(tid, (s) => {
            setStatuses((prev) => {
              const next = [...prev];
              next[task_ids.indexOf(tid)] = s;
              return next;
            });
          }),
        ),
      );
      onDone?.(finals);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div
      role="dialog"
      aria-modal="true"
      style={{
        position: "fixed",
        inset: 0,
        background: "rgba(0,0,0,0.45)",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        zIndex: 1000,
      }}
      onClick={onClose}
    >
      <div
        onClick={(e) => e.stopPropagation()}
        style={{
          width: "min(560px, 92vw)",
          background: "var(--surface, white)",
          borderRadius: 12,
          padding: 24,
          boxShadow: "0 24px 48px rgba(0,0,0,0.18)",
        }}
      >
        <h2 style={{ fontSize: 18, fontWeight: 700, marginBottom: 6 }}>
          Import from Notion
        </h2>
        <p style={{ fontSize: 13, color: "var(--muted, #6b7280)", marginBottom: 12 }}>
          Paste one or more Notion <strong>page</strong> or{" "}
          <strong>database</strong> URLs (one per line). Pages with
          subpages are imported recursively into a folder; databases
          become tables.
        </p>
        <p
          style={{
            fontSize: 12,
            color: "var(--muted, #6b7280)",
            marginBottom: 16,
            padding: 8,
            background: "var(--info-bg, rgba(37,99,235,0.06))",
            borderRadius: 6,
          }}
        >
          Notion shares are per-resource. Open each page or database in
          Notion → ⋯ → Add connections → choose your Stash connection.
          Anything not shared will fail with a 404.
        </p>

        <form onSubmit={onSubmit} style={{ display: "flex", flexDirection: "column", gap: 12 }}>
          <label style={{ fontSize: 13 }}>
            Pages or databases
            <textarea
              required
              value={raw}
              onChange={(e) => setRaw(e.target.value)}
              placeholder="https://www.notion.so/My-Page-abcdef123…"
              rows={6}
              disabled={submitting}
              style={{
                display: "block",
                width: "100%",
                marginTop: 4,
                padding: "8px 10px",
                borderRadius: 6,
                border: "1px solid var(--border, #d1d5db)",
                fontFamily: "var(--font-mono, monospace)",
                fontSize: 12,
              }}
            />
          </label>

          {statuses.length > 0 && (
            <div
              style={{
                fontSize: 13,
                padding: 8,
                borderRadius: 6,
                background: "var(--info-bg, rgba(37,99,235,0.08))",
                maxHeight: 180,
                overflow: "auto",
              }}
            >
              {statuses.map((s, i) =>
                s ? (
                  <div key={i}>
                    #{i + 1}: <strong>{s.state}</strong>
                    {s.error ? <span> — {s.error}</span> : null}
                  </div>
                ) : (
                  <div key={i}>
                    #{i + 1}: pending…
                  </div>
                ),
              )}
            </div>
          )}

          {error && (
            <div
              style={{
                fontSize: 13,
                padding: 8,
                borderRadius: 6,
                background: "rgba(220,38,38,0.08)",
                color: "rgb(185,28,28)",
              }}
            >
              {error}
            </div>
          )}

          <div style={{ display: "flex", justifyContent: "flex-end", gap: 8, marginTop: 4 }}>
            <button
              type="button"
              onClick={onClose}
              disabled={submitting}
              style={{
                padding: "8px 14px",
                borderRadius: 6,
                border: "1px solid var(--border, #d1d5db)",
                background: "transparent",
                cursor: submitting ? "wait" : "pointer",
              }}
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={submitting || !raw.trim()}
              style={{
                padding: "8px 14px",
                borderRadius: 6,
                border: "1px solid var(--accent, #2563eb)",
                background: "var(--accent, #2563eb)",
                color: "white",
                cursor: submitting ? "wait" : !raw.trim() ? "not-allowed" : "pointer",
                opacity: !raw.trim() ? 0.6 : 1,
              }}
            >
              {submitting ? "Importing…" : "Import"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
