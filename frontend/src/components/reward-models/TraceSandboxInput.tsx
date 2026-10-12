"use client";

import { useEffect, useRef, useState } from "react";
import { Upload } from "lucide-react";
import { Button } from "@/components/ui/button";
import { rmGetTrace, rmListTraces } from "@/lib/api";
import type { RmTraceSummary } from "@/lib/types";
import { errorMessage } from "./rm-text";

const MAX_BYTES = 2 * 1024 * 1024;

export default function TraceSandboxInput({ disabled, label = "Trace", onChange }: {
  disabled?: boolean; label?: string; onChange: (trace: string | Record<string, unknown>) => void;
}) {
  const fileInput = useRef<HTMLInputElement>(null);
  const [name, setName] = useState("");
  const [preview, setPreview] = useState("");
  const [choosing, setChoosing] = useState(false);
  const [query, setQuery] = useState("");
  const [traces, setTraces] = useState<RmTraceSummary[]>([]);
  const [loading, setLoading] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    if (!choosing) return;
    let cancelled = false;
    const timer = setTimeout(() => {
      setLoading(true); setError(null);
      void rmListTraces(25, 0, query).then((result) => {
        if (!cancelled) setTraces(result.traces);
      }).catch((e) => { if (!cancelled) setError(errorMessage(e)); })
        .finally(() => { if (!cancelled) setLoading(false); });
    }, 200);
    return () => { cancelled = true; clearTimeout(timer); };
  }, [choosing, query]);

  function accept(trace: string | Record<string, unknown>, title: string) {
    onChange(trace); setName(title);
    setPreview(typeof trace === "string" ? trace : JSON.stringify(trace, null, 2));
    setChoosing(false); setError(null);
  }
  async function upload(file: File) {
    setBusy(true); setError(null);
    try {
      if (file.size > MAX_BYTES) throw new Error("Choose a trace under 2 MB.");
      const text = await file.text();
      if (!text.trim()) throw new Error("This trace is empty.");
      if (/\.jsonl?$/i.test(file.name)) {
        const parsed: unknown = file.name.toLowerCase().endsWith(".jsonl")
          ? { events: text.split(/\r?\n/).filter((line) => line.trim()).map((line) => JSON.parse(line)) }
          : JSON.parse(text);
        if (Array.isArray(parsed)) accept({ events: parsed }, file.name);
        else if (parsed && typeof parsed === "object") accept(parsed as Record<string, unknown>, file.name);
        else throw new Error("A JSON trace must contain an object or an array of events.");
      } else accept(text, file.name);
    } catch (e) { setError(errorMessage(e)); }
    finally { setBusy(false); if (fileInput.current) fileInput.current.value = ""; }
  }
  async function choose(trace: RmTraceSummary) {
    setBusy(true); setError(null);
    try {
      const detail = await rmGetTrace(trace.id);
      accept({ title: detail.title, metadata: detail.metadata, steps: detail.steps }, trace.title);
    } catch (e) { setError(errorMessage(e)); }
    finally { setBusy(false); }
  }
  return <section className="space-y-3" aria-label={label}>
    <div className="py-2">
      {label !== "Trace" && <p className="mb-2 text-xs font-medium">{label}</p>}
      <div className="flex flex-wrap gap-2">
        <Button size="sm" variant="outline" type="button" disabled={disabled || busy} onClick={() => fileInput.current?.click()}><Upload />Upload a trace</Button>
        <Button size="sm" type="button" variant="outline" disabled={disabled || busy} onClick={() => setChoosing(!choosing)}>Use an existing trace</Button>
      </div>
      <input ref={fileInput} type="file" aria-label={`Upload ${label.toLowerCase()}`} accept=".json,.jsonl,.txt,.md" className="sr-only" disabled={disabled || busy} onChange={(e) => { const file = e.target.files?.[0]; if (file) void upload(file); }} />
      <p className="mt-3 text-xs text-muted-foreground">JSON, JSONL, or text transcript.</p>
    </div>
    {choosing && <div className="space-y-2 rounded-md border border-border p-3">
      <input aria-label="Search existing traces" placeholder="Search traces…" value={query} disabled={disabled || busy} onChange={(e) => setQuery(e.target.value)} className="w-full rounded border border-border p-2 text-sm" />
      {loading ? <p role="status" className="text-xs">Loading traces…</p> : traces.length ? <ul className="max-h-48 overflow-auto">{traces.map((trace) => <li key={trace.id}><button type="button" disabled={disabled || busy} className="w-full cursor-pointer rounded p-2 text-left text-sm hover:bg-muted" onClick={() => void choose(trace)}>{trace.title} <span className="text-xs text-muted-foreground">· {trace.step_count} steps</span></button></li>)}</ul> : <p className="text-xs text-muted-foreground">No matching traces.</p>}
    </div>}
    {busy && <p role="status" className="text-xs">Reading trace…</p>}
    {error && <p role="alert" className="text-xs text-red-600">{error}</p>}
    {name && <details open className="border-y border-border py-3"><summary className="cursor-pointer text-xs font-medium">{name}</summary><pre className="mt-2 max-h-64 overflow-auto whitespace-pre-wrap break-all text-xs text-muted-foreground">{preview}</pre></details>}
  </section>;
}
