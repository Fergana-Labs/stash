"use client";

import { ObsidianIcon } from "@/components/integrations/BrandIcons";
import ObsidianVaultDropZone from "@/components/import/ObsidianVaultDropZone";

type Props = {
  workspaceId: string;
  onUploaded: () => void;
  onClose: () => void;
};

export default function ObsidianImportDialog({
  workspaceId,
  onUploaded,
  onClose,
}: Props) {
  return (
    <div
      role="dialog"
      aria-modal="true"
      className="fixed inset-0 z-[1000] flex items-center justify-center bg-black/45"
      onClick={onClose}
    >
      <div
        onClick={(e) => e.stopPropagation()}
        className="flex w-[min(640px,92vw)] max-h-[80vh] flex-col rounded-xl bg-surface shadow-[0_24px_48px_rgba(0,0,0,0.18)]"
      >
        <div className="flex items-start gap-3 border-b border-border px-6 py-4">
          <ObsidianIcon size={24} className="mt-0.5" />
          <div className="flex-1">
            <h2 className="text-[15px] font-semibold text-foreground">
              Import from Obsidian
            </h2>
            <p className="mt-0.5 text-[12.5px] text-muted">
              Drag your vault folder onto the drop zone, or click to pick it.
              Folder structure is preserved; every <code>.md</code> becomes a
              collaboratively-edited page.
            </p>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="rounded-md p-1 text-muted hover:bg-raised hover:text-foreground"
            aria-label="Close"
          >
            ✕
          </button>
        </div>

        <div className="px-6 py-5">
          <ObsidianVaultDropZone
            workspaceId={workspaceId}
            onUploaded={() => onUploaded()}
          />
        </div>

        <div className="border-t border-border px-6 py-3 flex justify-end">
          <button
            type="button"
            onClick={onClose}
            className="rounded-md border border-border bg-base px-3 py-1.5 text-[12.5px] font-medium text-foreground hover:bg-raised"
          >
            Done
          </button>
        </div>
      </div>
    </div>
  );
}
