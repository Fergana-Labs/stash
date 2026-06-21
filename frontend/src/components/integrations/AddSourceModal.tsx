"use client";

import { useEffect } from "react";

import SourceConnectorList from "./SourceConnectorList";

export default function AddSourceModal({
  returnTo,
  onClose,
}: {
  returnTo: string;
  onClose: () => void;
}) {
  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  return (
    <div
      className="fixed inset-0 z-50 flex cursor-pointer items-center justify-center bg-black/40 p-4"
      onClick={onClose}
    >
      <div
        className="scroll-thin max-h-[85vh] w-full max-w-lg overflow-y-auto rounded-2xl border border-border bg-base p-5 shadow-xl"
        onClick={(event) => event.stopPropagation()}
      >
        <div className="mb-4 flex items-start justify-between">
          <div>
            <h2 className="font-display text-[18px] font-bold text-foreground">Connect a source</h2>
            <p className="mt-0.5 text-[12.5px] text-muted">
              Connect an account; add specific projects from its page.
            </p>
          </div>
          <button
            type="button"
            onClick={onClose}
            aria-label="Close"
            className="cursor-pointer rounded-md px-2 py-1 text-[18px] leading-none text-muted hover:bg-raised hover:text-foreground"
          >
            ×
          </button>
        </div>
        <SourceConnectorList returnTo={returnTo} />
      </div>
    </div>
  );
}
