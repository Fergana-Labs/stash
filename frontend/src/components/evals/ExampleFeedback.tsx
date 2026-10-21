"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { Button } from "@/components/ui/button";
import { imEditExample } from "@/lib/intuition-api";
import { errorMessage } from "@/components/reward-models/rm-text";
import { evalInputClass } from "./eval-ui";

export default function ExampleFeedback({ modelId, exampleId, note, disabled, onSaved }: { modelId: string; exampleId: string; note: string; disabled: boolean; onSaved: () => Promise<void> }) {
  const [value, setValue] = useState(note);
  const [error, setError] = useState("");
  const [saving, setSaving] = useState(false);
  const saved = useRef(note);
  const queue = useRef<Promise<void>>(Promise.resolve());
  const save = useCallback((next: string) => {
    queue.current = queue.current.catch(() => {}).then(async () => {
      if (next === saved.current) return;
      setSaving(true);
      try { await imEditExample(modelId, exampleId, { note: next }); saved.current = next; setError(""); await onSaved(); }
      catch (e) { setError(errorMessage(e)); }
      finally { setSaving(false); }
    });
    return queue.current;
  }, [modelId, exampleId, onSaved]);
  useEffect(() => {
    if (value === saved.current) return;
    const timer = setTimeout(() => { void save(value); }, 500);
    return () => clearTimeout(timer);
  }, [value, save]);
  return <div className="space-y-2"><textarea aria-label={`Feedback for example ${exampleId}`} maxLength={2000} rows={3} className={evalInputClass} disabled={disabled} value={value} onChange={(event) => setValue(event.target.value)} onBlur={() => { void save(value); }} placeholder="Explain what makes this good or bad…" />{saving && <p role="status" className="text-[11px] text-muted-foreground">Saving feedback…</p>}{error && <div className="space-y-1"><p role="alert" className="text-xs text-destructive">{error}</p><Button size="xs" variant="outline" onClick={() => { void save(value); }}>Retry feedback</Button></div>}</div>;
}
