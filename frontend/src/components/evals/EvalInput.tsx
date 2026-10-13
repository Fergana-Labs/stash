"use client";

import { useState } from "react";
import { Button } from "@/components/ui/button";
import TraceSandboxInput from "@/components/reward-models/TraceSandboxInput";
import { errorMessage } from "@/components/reward-models/rm-text";
import { evalInputClass as inputClass } from "./eval-ui";
import { evalReadFile, type Item } from "@/lib/intuition-api";
import ItemView from "@/components/intuitions/ItemView";
import type { RmTraceDetail } from "@/lib/types";

export default function EvalInput({ initialItem = null, onChange, onTrace, onDetail, disabled = false }: { initialItem?: Item | null; onChange: (item: Item | null) => void; onTrace?: (id: string | null) => void; onDetail?: (detail: RmTraceDetail | null) => void; disabled?: boolean }) {
  const [mode, setMode] = useState("text");
  const [text, setText] = useState(() => initialItem === null ? "" : typeof initialItem === "string" ? initialItem : JSON.stringify(initialItem, null, 2));
  const [file, setFile] = useState<Item | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  return <div className="space-y-3">
    <div className="flex gap-2" role="group" aria-label="Input source">{["text", "file", "trace"].map((value) => <Button key={value} size="xs" variant={mode === value ? "secondary" : "ghost"} disabled={disabled || busy} aria-pressed={mode === value} onClick={() => { if (mode === value) return; setMode(value); setText(""); setFile(null); setError(""); onChange(null); onTrace?.(null); onDetail?.(null); }}>{value === "text" ? "Paste output" : value === "file" ? "Upload file" : "Choose trace"}</Button>)}</div>
    {mode === "text" ? <textarea aria-label="Example output" rows={5} placeholder="Paste an output, conversation, or JSON…" className={inputClass} value={text} disabled={disabled} onChange={(e) => {
      const value = e.target.value;
      setText(value); setError("");
      if (!value.trim()) { onChange(null); return; }
      if (initialItem !== null && typeof initialItem !== "string") {
        try {
          const parsed: unknown = JSON.parse(value);
          if (parsed === null || typeof parsed !== "object" || Array.isArray(parsed)) throw new Error("Expected a JSON object");
          onChange(parsed as Item);
        } catch { setError("Enter a valid JSON object to evaluate this input."); onChange(null); }
      } else onChange(value);
    }} /> : mode === "file" ? <>
      <input aria-label="Upload eval input" type="file" accept=".txt,.md,.json,.jsonl,.ndjson,.pdf,.docx,.pptx,.png,.jpg,.jpeg,.webp,.gif" disabled={disabled || busy} className="text-xs" onChange={async (event) => {
        const selected = event.target.files?.[0]; if (!selected) return;
        onChange(null); setFile(null); setError("");
        if (selected.size > 2 * 1024 * 1024) { setError("Choose a file smaller than 2 MB"); return; }
        setBusy(true);
        try { const item = await evalReadFile(selected); setFile(item); onChange(item); }
        catch (e) { setError(errorMessage(e)); }
        finally { setBusy(false); }
      }} />
      <p className="text-xs text-muted-foreground">Images use a visual description. PDFs and slide decks use extracted text; upload slide screenshots to evaluate design.</p>
      {busy && <p role="status" className="text-xs">Reading file…</p>}{file && <ItemView item={file} />}
    </> : <TraceSandboxInput disabled={disabled} onChange={onChange} onSelectionChange={(trace) => { onChange(null); onTrace?.(trace.id); onDetail?.(null); }} onTraceChange={onDetail} selectionOnly />}
    {error && <p role="alert" className="text-xs text-destructive">{error}</p>}
  </div>;
}
