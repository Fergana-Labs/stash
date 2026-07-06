"use client";

import { useEffect, useState } from "react";
import { Loader2 } from "lucide-react";

import { machineFsRead, machineSaveToStash, type MachineFile } from "@/lib/api";

// Read-only view of a file on the user's cloud computer. The machine owns the
// file; "Save to Stash" copies it into the DB through the normal upload path
// (that copy is the only way machine bytes become shareable Stash content).
export default function MachineFileView({ path }: { path: string }) {
  const [file, setFile] = useState<MachineFile | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [savedUrl, setSavedUrl] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    machineFsRead(path)
      .then((f) => { if (!cancelled) setFile(f); })
      .catch((e) => { if (!cancelled) setError(e instanceof Error ? e.message : String(e)); });
    return () => { cancelled = true; };
  }, [path]);

  async function saveToStash() {
    setSaving(true);
    setError(null);
    try {
      const saved = await machineSaveToStash(path);
      setSavedUrl(saved.app_url);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="mx-auto flex h-full w-full max-w-4xl flex-col px-6 py-4">
      <div className="mb-3 flex items-center justify-between gap-3">
        <div className="min-w-0">
          <div className="truncate font-mono text-[13px] text-foreground">~/{path}</div>
          <div className="text-[11.5px] text-muted-foreground">
            On your computer{file ? ` · ${file.size.toLocaleString()} bytes` : ""} · read-only
          </div>
        </div>
        <div className="flex shrink-0 items-center gap-2">
          {savedUrl ? (
            <a href={savedUrl} className="rounded-md border border-border px-3 py-1.5 text-[12.5px] font-medium text-[var(--color-brand-700)] hover:bg-surface">
              Saved — open in Stash
            </a>
          ) : (
            <button
              type="button"
              onClick={() => void saveToStash()}
              disabled={saving || !file}
              className="cursor-pointer rounded-md bg-brand px-3 py-1.5 text-[12.5px] font-medium text-white hover:bg-brand-hover disabled:cursor-not-allowed disabled:opacity-60"
            >
              {saving ? "Saving…" : "Save to Stash"}
            </button>
          )}
        </div>
      </div>

      {error && (
        <div className="rounded-lg border border-error/30 bg-error/10 px-3 py-2 text-[12px] text-error">{error}</div>
      )}
      {!file && !error && (
        <div className="flex items-center gap-2 text-[13px] text-muted-foreground">
          <Loader2 className="h-4 w-4 animate-spin" /> Reading from your computer…
        </div>
      )}
      {file?.text !== undefined && (
        <pre className="scroll-thin min-h-0 flex-1 overflow-auto rounded-lg border border-border bg-surface p-4 font-mono text-[12.5px] leading-relaxed whitespace-pre-wrap text-foreground">
          {file.text}
        </pre>
      )}
      {file && file.text === undefined && (
        <div className="rounded-lg border border-border bg-surface px-4 py-6 text-center text-[13px] text-muted-foreground">
          Binary file — save it to Stash to preview or share it.
        </div>
      )}
    </div>
  );
}
