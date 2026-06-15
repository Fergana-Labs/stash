"use client";

import { useEffect, useRef, useState } from "react";

import {
  ExportFormat,
  exportPage,
  waitForTask,
} from "@/lib/integrations";

type Props = {
  pageId: string;
  layout?: string | null;
  contentType?: string | null;
};

const FORMATS: {
  value: ExportFormat;
  label: string;
  help: string;
  busyCopy: string;
}[] = [
  {
    value: "pdf",
    label: "Download PDF",
    help: "Single PDF, one page per slide",
    busyCopy: "Rendering PDF…",
  },
  {
    value: "pptx",
    label: "Download PPTX",
    help: "Editable in PowerPoint / Keynote",
    busyCopy: "Building PPTX…",
  },
  {
    value: "gslides",
    label: "Open in Google Slides",
    help: "Uploads to your Drive — requires Google connection",
    busyCopy: "Uploading to Google Drive…",
  },
];

function busyCopyFor(format: ExportFormat): string {
  return FORMATS.find((f) => f.value === format)?.busyCopy ?? "Working…";
}

type ExportResult = {
  format: ExportFormat;
  downloadUrl?: string;
  driveWebLink?: string;
};

function Spinner() {
  return (
    <svg
      className="h-3.5 w-3.5 animate-spin text-brand"
      viewBox="0 0 24 24"
      fill="none"
      aria-hidden
    >
      <circle
        cx="12"
        cy="12"
        r="10"
        stroke="currentColor"
        strokeOpacity="0.25"
        strokeWidth="4"
      />
      <path
        d="M22 12a10 10 0 0 1-10 10"
        stroke="currentColor"
        strokeWidth="4"
        strokeLinecap="round"
      />
    </svg>
  );
}

async function triggerDownload(url: string) {
  // Fetch as a blob so the browser saves the file instead of navigating
  // to it. Works because MinIO returns Access-Control-Allow-Origin for
  // our dev origin; a same-origin signed URL would also work.
  const filename = url.split("/").pop()?.split("?")[0] || "deck.pdf";
  const resp = await fetch(url, { credentials: "omit" });
  if (!resp.ok) throw new Error(`download failed: ${resp.status}`);
  const blob = await resp.blob();
  const objectUrl = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = objectUrl;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(objectUrl);
}

export default function ExportDeckButton({ pageId, layout, contentType }: Props) {
  const [open, setOpen] = useState(false);
  const [busyFormat, setBusyFormat] = useState<ExportFormat | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<ExportResult | null>(null);
  const ref = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    if (!open && !result && !error) return;
    function onDocClick(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) {
        setOpen(false);
        setResult(null);
        setError(null);
      }
    }
    document.addEventListener("mousedown", onDocClick);
    return () => document.removeEventListener("mousedown", onDocClick);
  }, [open, result, error]);

  if (contentType !== "html" || layout !== "fixed-aspect") return null;

  async function runExport(format: ExportFormat) {
    setBusyFormat(format);
    setError(null);
    setResult(null);
    setOpen(false);
    try {
      const { task_id } = await exportPage(pageId, format);
      const final = await waitForTask(task_id);
      if (final.state === "FAILURE") {
        setError(final.error || "Export failed");
        return;
      }
      const r = (final.result || {}) as {
        download_url?: string;
        drive_web_link?: string;
      };
      setResult({
        format,
        downloadUrl: r.download_url,
        driveWebLink: r.drive_web_link,
      });
      // For local files we fetch the blob and trigger a download so the
      // browser saves the file instead of navigating away (a direct
      // window.location to a PDF/PPTX opens it inline or replaces the
      // page). For Google Slides we open the Drive URL in a new tab.
      if (r.download_url) {
        await triggerDownload(r.download_url);
      } else if (r.drive_web_link) {
        window.open(r.drive_web_link, "_blank", "noopener,noreferrer");
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusyFormat(null);
    }
  }

  return (
    <div ref={ref} className="relative inline-block">
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        disabled={!!busyFormat}
        className="inline-flex cursor-pointer items-center gap-2 rounded-md border border-border bg-surface px-3 py-1.5 text-[13px] font-medium text-foreground hover:bg-raised disabled:cursor-wait disabled:opacity-80"
      >
        {busyFormat && <Spinner />}
        {busyFormat ? busyCopyFor(busyFormat) : "Export deck"}
      </button>
      {open && (
        <div
          role="menu"
          className="absolute right-0 top-[calc(100%+6px)] z-20 min-w-[260px] rounded-lg border border-border bg-surface p-1.5 shadow-[0_12px_32px_rgba(0,0,0,0.12)]"
        >
          {FORMATS.map((f) => (
            <button
              key={f.value}
              role="menuitem"
              onClick={() => runExport(f.value)}
              className="block w-full cursor-pointer rounded-md px-2.5 py-2 text-left transition hover:bg-raised"
            >
              <div className="text-[13px] font-medium text-foreground">{f.label}</div>
              <div className="mt-0.5 text-[12px] text-muted">{f.help}</div>
            </button>
          ))}
        </div>
      )}
      {busyFormat && !result && !error && (
        <div className="absolute right-0 top-[calc(100%+6px)] z-20 inline-flex items-center gap-2 rounded-md border border-border bg-surface px-3 py-2 text-[12.5px] text-foreground shadow-[0_8px_20px_rgba(0,0,0,0.08)]">
          <Spinner />
          <span>{busyCopyFor(busyFormat)}</span>
          {busyFormat === "gslides" && (
            <span className="text-muted">this takes ~20s</span>
          )}
        </div>
      )}
      {result && (
        <div className="absolute right-0 top-[calc(100%+6px)] z-20 min-w-[260px] rounded-md border border-border bg-surface p-3 text-[12.5px] text-foreground shadow-[0_12px_32px_rgba(0,0,0,0.12)]">
          <div className="mb-1.5 font-medium">
            {result.format === "gslides"
              ? "Uploaded to Google Drive"
              : `${result.format.toUpperCase()} ready`}
          </div>
          {result.driveWebLink && (
            <a
              href={result.driveWebLink}
              target="_blank"
              rel="noopener noreferrer"
              className="text-brand hover:underline"
            >
              Open in Google Slides →
            </a>
          )}
          {result.downloadUrl && (
            <a
              href={result.downloadUrl}
              className="text-brand hover:underline"
            >
              Download again
            </a>
          )}
          <button
            type="button"
            onClick={() => setResult(null)}
            className="ml-3 cursor-pointer text-muted hover:text-foreground"
          >
            Dismiss
          </button>
        </div>
      )}
      {error && (
        <div className="absolute right-0 top-[calc(100%+6px)] z-20 max-w-[360px] rounded-md bg-red-50 px-3 py-2 text-[12.5px] text-red-700 shadow-sm">
          {error}
          <button
            type="button"
            onClick={() => setError(null)}
            className="ml-2 cursor-pointer underline"
          >
            Dismiss
          </button>
        </div>
      )}
    </div>
  );
}
