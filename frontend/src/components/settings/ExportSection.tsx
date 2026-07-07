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
    <section className="rounded-2xl border border-border bg-surface p-6 space-y-4">
      <div>
        <h2 className="text-base font-semibold text-foreground">Export everything</h2>
        <p className="text-xs text-muted-foreground mt-0.5">
          Download your whole Stash as a zip of standard files — pages as Markdown/HTML,
          uploads as their original bytes. Your data is never locked in.
        </p>
      </div>
      {error && <p className="text-xs text-error">{error}</p>}
      <button
        type="button"
        onClick={handleExport}
        disabled={exporting}
        className="cursor-pointer bg-brand hover:bg-brand-hover disabled:opacity-60 text-white text-sm font-semibold px-4 py-2 rounded-lg transition-colors"
      >
        {exporting ? "Packaging…" : "Download export"}
      </button>
    </section>
  );
}
