"use client";

import { useEffect, useRef, useState } from "react";

import {
  ExportFormat,
  TaskStatus,
  exportPage,
  waitForTask,
} from "@/lib/integrations";

type Props = {
  pageId: string;
  /** Hide when the page isn't a fixed-aspect slide deck. */
  layout?: string | null;
  contentType?: string | null;
};

const FORMATS: { value: ExportFormat; label: string; help: string }[] = [
  { value: "pdf", label: "Download PDF", help: "Single PDF, one page per slide" },
  { value: "pptx", label: "Download PPTX", help: "Editable in PowerPoint / Keynote" },
  {
    value: "gslides",
    label: "Open in Google Slides",
    help: "Uploads to your Drive — requires Google connection",
  },
];

/**
 * Small popover button that lives next to a fixed-aspect slide-deck
 * page. Three actions, one shape:
 *   PDF / PPTX  → triggers a download once the task completes.
 *   gslides     → opens the resulting Drive URL in a new tab.
 *
 * Originally planned inside StashShareModal, but the modal is a
 * multi-item share/publish workflow — a per-page export is a cleaner
 * fit alongside the page view.
 */
export default function ExportDeckButton({ pageId, layout, contentType }: Props) {
  const [open, setOpen] = useState(false);
  const [busyFormat, setBusyFormat] = useState<ExportFormat | null>(null);
  const [status, setStatus] = useState<TaskStatus | null>(null);
  const [error, setError] = useState<string | null>(null);
  const ref = useRef<HTMLDivElement | null>(null);

  // Click-outside to close.
  useEffect(() => {
    if (!open) return;
    function onDocClick(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    }
    document.addEventListener("mousedown", onDocClick);
    return () => document.removeEventListener("mousedown", onDocClick);
  }, [open]);

  if (contentType !== "html" || layout !== "fixed-aspect") return null;

  async function runExport(format: ExportFormat) {
    setBusyFormat(format);
    setStatus(null);
    setError(null);
    setOpen(false);
    try {
      const { task_id } = await exportPage(pageId, format);
      const final = await waitForTask(task_id, setStatus);
      if (final.state === "FAILURE") {
        setError(final.error || "Export failed");
        return;
      }
      const result = (final.result || {}) as {
        download_url?: string;
        drive_web_link?: string;
      };
      if (result.download_url) {
        window.location.href = result.download_url;
      } else if (result.drive_web_link) {
        window.open(result.drive_web_link, "_blank", "noopener,noreferrer");
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusyFormat(null);
    }
  }

  return (
    <div ref={ref} style={{ position: "relative", display: "inline-block" }}>
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        disabled={!!busyFormat}
        style={{
          padding: "6px 12px",
          borderRadius: 6,
          border: "1px solid var(--border, #d1d5db)",
          background: "var(--surface, #fff)",
          cursor: busyFormat ? "wait" : "pointer",
          fontSize: 13,
        }}
      >
        {busyFormat ? `Exporting ${busyFormat.toUpperCase()}…` : "Export deck"}
      </button>
      {open && (
        <div
          role="menu"
          style={{
            position: "absolute",
            top: "calc(100% + 6px)",
            right: 0,
            zIndex: 20,
            background: "var(--surface, #fff)",
            border: "1px solid var(--border, #e5e7eb)",
            borderRadius: 8,
            boxShadow: "0 12px 32px rgba(0,0,0,0.12)",
            minWidth: 240,
            padding: 6,
          }}
        >
          {FORMATS.map((f) => (
            <button
              key={f.value}
              role="menuitem"
              onClick={() => runExport(f.value)}
              style={{
                display: "block",
                width: "100%",
                textAlign: "left",
                padding: "8px 10px",
                background: "transparent",
                border: "none",
                borderRadius: 6,
                cursor: "pointer",
                fontSize: 13,
              }}
              onMouseEnter={(e) => {
                (e.currentTarget as HTMLButtonElement).style.background =
                  "var(--hover, rgba(0,0,0,0.04))";
              }}
              onMouseLeave={(e) => {
                (e.currentTarget as HTMLButtonElement).style.background = "transparent";
              }}
            >
              <div style={{ fontWeight: 500 }}>{f.label}</div>
              <div style={{ fontSize: 12, color: "var(--muted, #6b7280)", marginTop: 2 }}>
                {f.help}
              </div>
            </button>
          ))}
        </div>
      )}
      {status && busyFormat && (
        <div
          style={{
            position: "absolute",
            top: "calc(100% + 6px)",
            right: 0,
            fontSize: 12,
            color: "var(--muted, #6b7280)",
          }}
        >
          {status.state}…
        </div>
      )}
      {error && (
        <div
          style={{
            position: "absolute",
            top: "calc(100% + 6px)",
            right: 0,
            zIndex: 20,
            background: "rgba(220,38,38,0.08)",
            color: "rgb(185,28,28)",
            padding: 8,
            borderRadius: 6,
            fontSize: 13,
            maxWidth: 320,
          }}
        >
          {error}
        </div>
      )}
    </div>
  );
}
