"use client";

import { useEffect, useRef, useState } from "react";
import { MoreHorizontal, Upload } from "lucide-react";
import { Button } from "@/components/ui/button";
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger } from "@/components/ui/dropdown-menu";
import { rmGetTrace, rmListTraces } from "@/lib/api";
import type { RmTraceSummary } from "@/lib/types";
import { errorMessage } from "./rm-text";

const MAX_BYTES = 2 * 1024 * 1024;
type TraceItem = string | Record<string, unknown>;

export default function TraceSandboxInput({ disabled, label = "Trace", onChange }: {
  disabled?: boolean; label?: string; onChange: (trace: TraceItem) => void;
}) {
  const fileInput = useRef<HTMLInputElement>(null);
  const change = useRef(onChange);
  change.current = onChange;
  const selection = useRef(0);
  const [name, setName] = useState("");
  const [item, setItem] = useState<TraceItem | null>(null);
  const [query, setQuery] = useState("");
  const [traces, setTraces] = useState<RmTraceSummary[]>([]);
  const [selectedId, setSelectedId] = useState("");
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  function accept(trace: TraceItem, title: string) {
    change.current(trace); setName(title); setItem(trace); setError(null);
  }
  async function choose(trace: RmTraceSummary) {
    const request = ++selection.current;
    setBusy(true); setError(null);
    try {
      const detail = await rmGetTrace(trace.id);
      if (selection.current !== request) return;
      // Previously assigned rewards and annotations are not model input.
      const steps = detail.steps.map(({ id, index, role, content, tool_name, tool_input, tool_call_id }) => ({ id, index, role, content, tool_name, tool_input, tool_call_id }));
      accept({ title: detail.title, steps }, trace.title); setSelectedId(trace.id);
    } catch (e) { if (selection.current === request) setError(errorMessage(e)); }
    finally { if (selection.current === request) setBusy(false); }
  }
  const chooseRef = useRef(choose);
  chooseRef.current = choose;
  useEffect(() => {
    let cancelled = false;
    const timer = setTimeout(() => {
      setLoading(true);
      void rmListTraces(25, 0, query).then((result) => {
        if (cancelled) return;
        setTraces(result.traces);
        if (!selection.current && result.traces.length) void chooseRef.current(result.traces[0]);
      }).catch((e) => { if (!cancelled) setError(errorMessage(e)); })
        .finally(() => { if (!cancelled) setLoading(false); });
    }, 200);
    return () => { cancelled = true; clearTimeout(timer); };
  }, [query]);

  async function upload(file: File) {
    const request = ++selection.current;
    setBusy(true); setError(null);
    try {
      if (file.size > MAX_BYTES) throw new Error("Choose a trace under 2 MB.");
      const text = await file.text();
      if (selection.current !== request) return;
      if (!text.trim()) throw new Error("This trace is empty.");
      let parsed: unknown = text;
      if (/\.jsonl?$/i.test(file.name)) parsed = file.name.toLowerCase().endsWith(".jsonl")
        ? { events: text.split(/\r?\n/).filter((line) => line.trim()).map((line) => JSON.parse(line)) }
        : JSON.parse(text);
      if (Array.isArray(parsed)) accept({ events: parsed }, file.name);
      else if (typeof parsed === "string") accept(parsed, file.name);
      else if (parsed && typeof parsed === "object") accept(parsed as Record<string, unknown>, file.name);
      else throw new Error("A JSON trace must contain an object or an array of events.");
      setSelectedId("");
    } catch (e) { if (selection.current === request) setError(errorMessage(e)); }
    finally { if (selection.current === request) setBusy(false); if (fileInput.current) fileInput.current.value = ""; }
  }
  const steps = typeof item === "object" && item !== null && Array.isArray(item.steps) ? item.steps as Record<string, unknown>[] : null;
  return <section className="space-y-3" aria-label={label}>
    <div className="flex items-center gap-2">
      <select aria-label={`Choose ${label.toLowerCase()}`} value={selectedId} disabled={disabled || busy} onChange={(e) => { const trace = traces.find((trace) => trace.id === e.target.value); if (trace) void choose(trace); }} className="h-8 min-w-0 flex-1 rounded-md border border-border bg-background px-2 text-xs">
        <option value="">{name && !selectedId ? name : loading ? "Loading traces…" : "Choose an example trace"}</option>
        {selectedId && !traces.some((trace) => trace.id === selectedId) && <option value={selectedId}>{name}</option>}
        {traces.map((trace) => <option key={trace.id} value={trace.id}>{trace.title}</option>)}
      </select>
      <DropdownMenu><DropdownMenuTrigger asChild><Button type="button" variant="ghost" size="icon-sm" aria-label="Trace options" disabled={disabled || busy}><MoreHorizontal /></Button></DropdownMenuTrigger><DropdownMenuContent align="end"><DropdownMenuItem onSelect={() => fileInput.current?.click()}><Upload />Upload your own trace</DropdownMenuItem></DropdownMenuContent></DropdownMenu>
      <input ref={fileInput} type="file" aria-label={`Upload ${label.toLowerCase()}`} accept=".json,.jsonl,.txt,.md" className="sr-only" disabled={disabled || busy} onChange={(e) => { const file = e.target.files?.[0]; if (file) void upload(file); }} />
    </div>
    <input aria-label="Search existing traces" placeholder="Find a trace…" value={query} disabled={disabled || busy} onChange={(e) => setQuery(e.target.value)} className="h-7 w-full border-b border-border bg-transparent text-xs outline-none" />
    {busy && <p role="status" className="text-xs text-muted-foreground">Loading trace…</p>}
    {error && <p role="alert" className="text-xs text-red-600">{error}</p>}
    {!loading && !busy && !item && !traces.length && <p className="text-xs text-muted-foreground">No traces found. Upload one from the trace options menu.</p>}
    {item && <div className="max-h-[420px] overflow-auto border-y border-border" aria-label="Trace preview">
      {steps ? <div className="divide-y divide-border">{steps.map((step, index) => <article key={index} className="py-3"><p className="mb-2 text-[11px] font-medium text-muted-foreground">{index + 1} · {String(step.role ?? "message")}{step.tool_name ? ` → ${step.tool_name}` : ""}</p><p className="whitespace-pre-wrap break-words text-xs leading-relaxed">{String(step.content ?? "")}</p>{Boolean(step.tool_input) && <pre className="mt-2 whitespace-pre-wrap break-all text-[11px] text-muted-foreground">{JSON.stringify(step.tool_input, null, 2)}</pre>}</article>)}</div> : <pre className="py-3 whitespace-pre-wrap break-words text-xs">{typeof item === "string" ? item : JSON.stringify(item, null, 2)}</pre>}
    </div>}
  </section>;
}
