"use client";

import { useState } from "react";
import { fetchAuthed } from "../../lib/api";

export default function ExportSection() {
  const [exporting, setExporting] = useState(false);
  const [error, setError] = useState("");

  async function handleExport() {
    setExporting(true);
    setError("");
    try {
      const res = await fetchAuthed("/api/v1/me/export");
      if (!res.ok) throw new Error(`Export failed (${res.status})`);
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `stash-export-${new Date().toISOString().slice(0, 10)}.zip`;
      a.click();
      URL.revokeObjectURL(url);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Export failed");
    } finally {
      setExporting(false);
    }
  }

  return (
    <section className="space-y-3 rounded-lg border border-border bg-surface p-5">
      <div>
        <h2 className="text-base font-semibold text-foreground">Export your traces</h2>
        <p className="text-xs text-muted-foreground mt-0.5">
          Download everything in your Stash as a zip: your Memory wiki and other pages as
          plain Markdown/HTML, and your uploaded files as their original bytes. Your data
          is never locked in.
        </p>
      </div>
      {error && <p className="text-xs text-error">{error}</p>}
      <button
        type="button"
        onClick={handleExport}
        disabled={exporting}
        className="cursor-pointer rounded-md border border-border bg-background px-3 py-1.5 text-[13px] font-medium text-foreground transition-colors hover:bg-raised disabled:opacity-60"
      >
        {exporting ? "Packaging…" : "Download export"}
      </button>
    </section>
  );
}
