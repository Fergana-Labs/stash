"use client";

import { useState } from "react";

import { createFolder } from "@/lib/api";
import { GoogleDriveIcon } from "@/components/integrations/BrandIcons";
import { useGoogleDrivePicker } from "./useGoogleDrivePicker";

type Props = {
  workspaceId: string;
  folderId?: string | null;
  onDispatched?: (taskIds: string[]) => void;
  onClose: () => void;
};

/**
 * Tiny pre-picker dialog for Drive. Lets the user choose whether to drop
 * picked files into a new folder before we hand them off to Google's own
 * picker UI (which we can't extend with custom controls).
 */
export default function DriveImportDialog({
  workspaceId,
  folderId,
  onDispatched,
  onClose,
}: Props) {
  const [makeFolder, setMakeFolder] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const picker = useGoogleDrivePicker({
    workspaceId,
    folderId: folderId ?? null,
    onDispatched: (ids) => {
      onDispatched?.(ids);
      onClose();
    },
  });

  async function open() {
    setError(null);
    setSubmitting(true);
    try {
      let importFolderId = folderId ?? null;
      if (makeFolder) {
        const today = new Date().toISOString().slice(0, 10);
        const folder = await createFolder(
          workspaceId,
          `Drive import — ${today}`,
          folderId ?? undefined,
        );
        importFolderId = folder.id;
      }
      await picker.openPicker(importFolderId);
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
      className="fixed inset-0 z-[1000] flex items-center justify-center bg-black/45"
      onClick={onClose}
    >
      <div
        onClick={(e) => e.stopPropagation()}
        className="flex w-[min(480px,92vw)] flex-col rounded-xl bg-surface shadow-[0_24px_48px_rgba(0,0,0,0.18)]"
      >
        <div className="flex items-start gap-3 border-b border-border px-6 py-4">
          <GoogleDriveIcon size={24} />
          <div className="flex-1">
            <h2 className="text-[15px] font-semibold text-foreground">
              Import from Google Drive
            </h2>
            <p className="mt-0.5 text-[12.5px] text-muted">
              We'll open the Google file picker. Hold ⌘ or shift to select
              multiple files.
            </p>
          </div>
          <button
            type="button"
            onClick={onClose}
            disabled={submitting}
            className="rounded-md p-1 text-muted hover:bg-raised hover:text-foreground"
            aria-label="Close"
          >
            ✕
          </button>
        </div>

        <div className="px-6 py-4">
          <label className="flex cursor-pointer items-center gap-2 text-[13px] text-foreground">
            <input
              type="checkbox"
              checked={makeFolder}
              onChange={(e) => setMakeFolder(e.target.checked)}
              disabled={submitting}
              className="h-3.5 w-3.5"
              style={{ accentColor: "var(--color-brand)" }}
            />
            <span>
              Put inside a new folder{" "}
              <span className="text-muted">named</span>{" "}
              <span className="font-mono text-muted">
                Drive import — {new Date().toISOString().slice(0, 10)}
              </span>
            </span>
          </label>
          {error && (
            <div className="mt-3 rounded-md bg-red-50 px-3 py-2 text-[12.5px] text-red-700">
              {error}
            </div>
          )}
        </div>

        <div className="flex items-center justify-end gap-2 border-t border-border px-6 py-3">
          <button
            type="button"
            onClick={onClose}
            disabled={submitting}
            className="rounded-md border border-border bg-base px-3 py-1.5 text-[12.5px] font-medium text-foreground hover:bg-raised disabled:cursor-wait disabled:opacity-60"
          >
            Cancel
          </button>
          <button
            type="button"
            onClick={open}
            disabled={submitting}
            className="rounded-md bg-brand px-3 py-1.5 text-[12.5px] font-medium text-white hover:bg-brand-hover disabled:cursor-wait disabled:opacity-60"
          >
            {submitting ? "Opening…" : "Open Drive picker"}
          </button>
        </div>
      </div>
    </div>
  );
}
