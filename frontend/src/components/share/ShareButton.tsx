"use client";

import { useEffect, useState } from "react";

import {
  getObjectPermissions,
  ObjectVisibility,
  ShareableObjectType,
} from "../../lib/api";
import ShareSheet from "./ShareSheet";

interface Props {
  objectType: ShareableObjectType;
  objectId: string;
  label: string;
  variant?: "compact" | "prominent";
}

const VIS_DISPLAY: Record<ObjectVisibility, { icon: string; word: string }> = {
  inherit: { icon: "🔒", word: "Private" },
  private: { icon: "🔒", word: "Private" },
  link: { icon: "🔗", word: "Link" },
  public: { icon: "🌐", word: "Public" },
};

export default function ShareButton({
  objectType,
  objectId,
  label,
  variant = "compact",
}: Props) {
  const [open, setOpen] = useState(false);
  const [vis, setVis] = useState<ObjectVisibility | null>(null);

  // Re-read after the sheet closes so the trigger reflects edits made in the sheet.
  useEffect(() => {
    let cancelled = false;
    getObjectPermissions(objectType, objectId)
      .then((p) => {
        if (!cancelled) setVis(p.visibility);
      })
      .catch(() => {
        if (!cancelled) setVis(null);
      });
    return () => {
      cancelled = true;
    };
  }, [objectType, objectId, open]);

  const display = vis ? VIS_DISPLAY[vis] : null;

  if (variant === "prominent") {
    return (
      <div className="relative">
        <button
          onClick={() => setOpen((v) => !v)}
          className="inline-flex items-center gap-1.5 rounded-md border border-border bg-raised px-3 py-1.5 text-[12px] font-medium text-foreground transition-colors hover:border-foreground"
        >
          {display && <span aria-hidden>{display.icon}</span>}
          <span>Share</span>
          {display && (
            <span className="font-mono text-[10px] uppercase tracking-[0.08em] text-muted">
              {display.word}
            </span>
          )}
        </button>
        {open && (
          <ShareSheet
            objectType={objectType}
            objectId={objectId}
            objectLabel={label}
            onClose={() => setOpen(false)}
          />
        )}
      </div>
    );
  }

  return (
    <div className="relative">
      <button
        onClick={() => setOpen((v) => !v)}
        className="inline-flex items-center gap-1 rounded border border-border bg-raised px-2.5 py-1 font-mono text-[10px] uppercase tracking-[0.08em] text-foreground transition-colors hover:border-foreground"
      >
        {display && <span aria-hidden>{display.icon}</span>}
        <span>Share</span>
      </button>
      {open && (
        <ShareSheet
          objectType={objectType}
          objectId={objectId}
          objectLabel={label}
          onClose={() => setOpen(false)}
        />
      )}
    </div>
  );
}
