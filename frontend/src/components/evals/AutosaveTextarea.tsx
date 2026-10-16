"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { Button } from "@/components/ui/button";
import { errorMessage } from "@/components/reward-models/rm-text";
import { evalInputClass } from "./eval-ui";

/** Serialize writes and keep newer typing intact while an earlier save finishes. */
export default function AutosaveTextarea({ value: initial, save, onSaved, label, placeholder, rows = 3, maxLength = 2000, onChange }: {
  value: string; save: (value: string) => Promise<unknown>; onSaved: () => void;
  label: string; placeholder?: string; rows?: number; maxLength?: number; onChange?: (value: string) => void;
}) {
  const [value, setValue] = useState(initial);
  const [status, setStatus] = useState<"idle" | "pending" | "saving" | "saved" | "error">("idle");
  const [error, setError] = useState("");
  const latest = useRef(initial);
  const saved = useRef(initial);
  const writing = useRef<Promise<void> | null>(null);
  const callbacks = useRef({ save, onSaved });
  useEffect(() => { callbacks.current = { save, onSaved }; }, [save, onSaved]);
  const mounted = useRef(true);

  const flush = useCallback((): Promise<void> => {
    if (writing.current) return writing.current;
    if (latest.current === saved.current) return Promise.resolve();
    const run = async () => {
      while (latest.current !== saved.current) {
        const next = latest.current;
        if (mounted.current) { setStatus("saving"); setError(""); }
        try {
          await callbacks.current.save(next);
          saved.current = next;
          callbacks.current.onSaved();
        } catch (e) {
          if (mounted.current) { setError(errorMessage(e)); setStatus("error"); }
          return;
        }
      }
      if (mounted.current) setStatus("saved");
    };
    writing.current = run().finally(() => { writing.current = null; });
    return writing.current;
  }, []);

  useEffect(() => {
    mounted.current = true;
    return () => { mounted.current = false; void flush(); };
  }, [flush]);
  useEffect(() => {
    // External changes may refresh a clean field, but never replace unsaved typing.
    if (!writing.current && latest.current === saved.current) {
      latest.current = initial; saved.current = initial; setValue(initial);
    }
  }, [initial]);
  useEffect(() => {
    if (value === saved.current) return;
    const timer = setTimeout(() => { void flush(); }, 500);
    return () => clearTimeout(timer);
  }, [value, flush]);

  return <div className="space-y-1.5">
    <textarea aria-label={label} maxLength={maxLength} rows={rows} className={evalInputClass} placeholder={placeholder} value={value}
      onChange={(e) => { const next = e.target.value; latest.current = next; setValue(next); setStatus(next === saved.current ? "saved" : "pending"); setError(""); onChange?.(next); }}
      onBlur={() => { void flush(); }} />
    {status !== "idle" && status !== "error" && <p role="status" className="m-0 text-[11px] text-muted-foreground">{status === "saving" ? "Saving…" : status === "pending" ? "Unsaved changes" : "Saved"}</p>}
    {error && <div className="flex items-center gap-2"><p role="alert" className="m-0 text-xs text-destructive">{error}</p><Button size="xs" variant="outline" onClick={() => void flush()}>Retry save</Button></div>}
  </div>;
}
