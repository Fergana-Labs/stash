"use client";

import { useEffect, useRef, useState } from "react";
import { Check, Loader2, MoreHorizontal, Upload } from "lucide-react";
import { Button } from "@/components/ui/button";
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger } from "@/components/ui/dropdown-menu";
import { rmGetTrace, rmListTraces } from "@/lib/api";
import type { RmTraceDetail, RmTraceSummary } from "@/lib/types";
import { traceSourceName } from "./trace-sources";
import { errorMessage } from "./rm-text";
import { cn } from "@/lib/utils";

const MAX_BYTES = 2 * 1024 * 1024;
type TraceItem = string | Record<string, unknown>;

function traceItem(detail: RmTraceDetail): TraceItem {
  const steps = detail.steps.map(({ id, index, role, content, tool_name, tool_input, tool_call_id }) => ({ id, index, role, content, tool_name, tool_input, tool_call_id }));
  return { title: detail.title, steps };
}

export default function TraceSandboxInput({ disabled, label = "Trace", onChange, onTraceChange, onLoadingChange, onSelectionChange, importTrace, maxBytes = MAX_BYTES, scoreableOnly = false, selectionOnly = false }: {
  disabled?: boolean; label?: string; onChange: (trace: TraceItem) => void;
  onTraceChange?: (trace: RmTraceDetail | null, uploaded?: boolean) => void;
  importTrace?: (file: File) => Promise<RmTraceDetail>;
  maxBytes?: number;
  scoreableOnly?: boolean;
  selectionOnly?: boolean;
  onLoadingChange?: (loading: boolean) => void;
  onSelectionChange?: (trace: RmTraceSummary) => void;
}) {
  const fileInput = useRef<HTMLInputElement>(null);
  const change = useRef(onChange);
  change.current = onChange;
  const traceChange = useRef(onTraceChange);
  traceChange.current = onTraceChange;
  const loadingChange = useRef(onLoadingChange);
  loadingChange.current = onLoadingChange;
  const selection = useRef(0);
  const viewport = useRef<HTMLDivElement>(null);
  const sentinel = useRef<HTMLDivElement>(null);
  const pagePending = useRef(false);
  const [hasMore, setHasMore] = useState(false);
  const [name, setName] = useState("");
  const [item, setItem] = useState<TraceItem | null>(null);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [refresh, setRefresh] = useState(0);
  const [query, setQuery] = useState("");
  const [traces, setTraces] = useState<RmTraceSummary[]>([]);
  const [offset, setOffset] = useState(0);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  function accept(trace: TraceItem, title: string, id: string | null = null) {
    change.current(trace); setName(title); setItem(trace); setSelectedId(id); setError(null);
  }
  async function choose(trace: RmTraceSummary) {
    if (selectionOnly && trace.id === selectedId && item) return;
    const request = ++selection.current;
    setSelectedId(trace.id); setName(trace.title); setItem(null);
    onSelectionChange?.(trace);
    setBusy(true); loadingChange.current?.(true); setError(null);
    try {
      const detail = await rmGetTrace(trace.id);
      if (selection.current !== request) return;
      // Previously assigned rewards and annotations are not model input.
      accept(traceItem(detail), trace.title, trace.id);
      traceChange.current?.(detail);
    } catch (e) { if (selection.current === request) setError(errorMessage(e)); }
    finally { if (selection.current === request) { setBusy(false); loadingChange.current?.(false); } }
  }
  useEffect(() => {
    let cancelled = false;
    pagePending.current = true;
    const timer = setTimeout(() => {
      setLoading(true);
      void rmListTraces(25, offset, query).then((result) => {
        if (cancelled) return;
        const eligible = scoreableOnly ? result.traces.filter((trace) => trace.can_score !== false) : result.traces;
        setTraces((previous) => {
          const combined = offset === 0 ? eligible : [...previous, ...eligible];
          return [...new Map(combined.map((trace) => [trace.id, trace])).values()];
        });
        setTotal(result.total);
        // Pagination follows the server page, including any rows filtered out above.
        setHasMore(result.traces.length > 0 && offset + result.traces.length < result.total);
      }).catch((e) => { if (!cancelled) { setError(errorMessage(e)); setHasMore(false); } })
        .finally(() => { if (!cancelled) { pagePending.current = false; setLoading(false); } });
    }, offset === 0 ? 200 : 0);
    return () => { cancelled = true; clearTimeout(timer); };
  }, [query, offset, scoreableOnly, refresh]);

  function loadMore() {
    if (!hasMore || pagePending.current || disabled) return;
    pagePending.current = true;
    setLoading(true); setOffset((value) => value + 25);
  }
  useEffect(() => {
    if (!hasMore || loading || disabled || !sentinel.current || typeof IntersectionObserver === "undefined") return;
    const observer = new IntersectionObserver((entries) => {
      if (entries.some((entry) => entry.isIntersecting) && !pagePending.current) {
        pagePending.current = true;
        setLoading(true); setOffset((value) => value + 25);
      }
    }, { root: viewport.current, rootMargin: "120px" });
    observer.observe(sentinel.current);
    return () => observer.disconnect();
  }, [hasMore, loading, disabled]);

  async function upload(file: File) {
    const request = ++selection.current;
    setBusy(true); loadingChange.current?.(true); setError(null);
    try {
      if (file.size > maxBytes) throw new Error(`Choose a trace under ${maxBytes / (1024 * 1024)} MB.`);
      if (importTrace) {
        const detail = await importTrace(file);
        if (selection.current !== request) return;
        accept(traceItem(detail), detail.title, detail.id);
        traceChange.current?.(detail, true);
        setOffset(0); setTraces([]); setLoading(true); setRefresh((value) => value + 1);
        return;
      }
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

    } catch (e) { if (selection.current === request) setError(errorMessage(e)); }
    finally { if (selection.current === request) { setBusy(false); loadingChange.current?.(false); } if (fileInput.current) fileInput.current.value = ""; }
  }
  const steps = typeof item === "object" && item !== null && Array.isArray(item.steps) ? item.steps as Record<string, unknown>[] : null;
  return <section className="space-y-3" aria-label={label}>
    <div className="flex items-center gap-2">
      {item && !selectionOnly ? <><span className="min-w-0 flex-1 truncate text-xs font-medium" title={name}>{name}</span><Button type="button" variant="ghost" size="sm" disabled={disabled || busy} onClick={() => { ++selection.current; setItem(null); setSelectedId(null); setName(""); change.current(""); traceChange.current?.(null); }}>Change trace</Button></> : <input aria-label="Search existing traces" placeholder="Search traces…" value={query} disabled={disabled} onChange={(e) => { setQuery(e.target.value); setOffset(0); setTraces([]); setHasMore(false); setLoading(true); setError(null); viewport.current?.scrollTo?.({ top: 0 }); }} className="h-7 min-w-0 flex-1 rounded-md border border-border bg-transparent px-2 text-xs outline-none" />}
      <DropdownMenu><DropdownMenuTrigger asChild><Button type="button" variant="ghost" size="icon-sm" aria-label="Trace options" disabled={disabled || busy}>{busy ? <Loader2 role="status" aria-label="Loading trace" className="animate-spin" /> : <MoreHorizontal />}</Button></DropdownMenuTrigger><DropdownMenuContent align="end"><DropdownMenuItem onSelect={() => fileInput.current?.click()}><Upload />Upload your own trace</DropdownMenuItem></DropdownMenuContent></DropdownMenu>
      <input ref={fileInput} type="file" aria-label={`Upload ${label.toLowerCase()}`} accept=".json,.jsonl,.ndjson,.txt,.md" className="sr-only" disabled={disabled || busy} onChange={(e) => { const file = e.target.files?.[0]; if (file) void upload(file); }} />
    </div>
    {(!item || selectionOnly) && <div ref={viewport} role="region" aria-label="Available traces" tabIndex={0} className="max-h-[min(52vh,420px)] overflow-auto overscroll-contain border-y border-border" onScroll={(event) => { const node = event.currentTarget; if (node.scrollHeight - node.scrollTop - node.clientHeight < 120) loadMore(); }}>
      <table aria-label="Choose a trace" className="w-full table-fixed border-collapse text-left text-xs">
        <colgroup><col /><col className="w-28" /><col className="w-14" /></colgroup>
        <thead className="sticky top-0 z-10 h-7 border-b border-border bg-background text-[11px] text-muted-foreground"><tr><th className="px-2 font-medium">Trace</th><th className="px-2 font-medium">Source</th><th className="px-2 text-right font-medium">Steps</th></tr></thead>
        <tbody>{loading && !traces.length ? <tr><td colSpan={3} className="px-2 py-3 text-muted-foreground">Loading traces…</td></tr> : traces.map((trace) => <tr key={trace.id} aria-selected={selectionOnly ? selectedId === trace.id : undefined} onClick={() => { if (!disabled) void choose(trace); }} className={cn("h-7 cursor-pointer border-b border-border-subtle last:border-0 hover:bg-surface/60 focus-within:bg-surface/60", selectionOnly && selectedId === trace.id && "bg-brand-500/10")}>
          <td className="px-2"><button type="button" aria-label={`Choose ${trace.title}`} aria-pressed={selectionOnly ? selectedId === trace.id : undefined} title={trace.title} disabled={disabled} onClick={(e) => { e.stopPropagation(); void choose(trace); }} className="flex h-7 w-full cursor-pointer items-center gap-1.5 text-left font-medium hover:text-brand-600 disabled:cursor-default">{selectionOnly && selectedId === trace.id && <Check className="h-3 w-3 shrink-0 text-brand-600" />}<span className="truncate">{trace.title}</span></button></td>
          <td className="px-2 text-muted-foreground"><span className="block truncate" title={traceSourceName(trace)}>{traceSourceName(trace)}</span></td><td className="px-2 text-right tabular-nums text-muted-foreground">{trace.step_count}</td>
        </tr>)}</tbody>
      </table>
      <div ref={sentinel} className="h-1" />
      {loading && traces.length > 0 && <p role="status" className="px-2 py-2 text-xs text-muted-foreground">Loading more traces…</p>}
    </div>}
    {(!item || selectionOnly) && total > 25 && <p className="text-[11px] text-muted-foreground">{traces.length} of {total} traces{hasMore ? " · Scroll for more" : ""}</p>}
    {error && <p role="alert" className="text-xs text-red-600">{error}</p>}
    {!loading && !hasMore && !busy && !item && !traces.length && <p className="text-xs text-muted-foreground">No traces found. Upload one from the trace options menu.</p>}
    {selectionOnly && item && !traces.some((trace) => trace.id === selectedId) && <p className="text-xs text-muted-foreground">Selected: {name}</p>}
    {item && !selectionOnly && <div className="max-h-[420px] overflow-auto border-y border-border" aria-label="Trace preview">
      {steps ? <div className="divide-y divide-border">{steps.map((step, index) => <article key={index} className="py-3"><p className="mb-2 text-[11px] font-medium text-muted-foreground">{index + 1} · {String(step.role ?? "message")}{step.tool_name ? ` → ${step.tool_name}` : ""}</p><p className="whitespace-pre-wrap break-words text-xs leading-relaxed">{String(step.content ?? "")}</p>{Boolean(step.tool_input) && <pre className="mt-2 whitespace-pre-wrap break-all text-[11px] text-muted-foreground">{JSON.stringify(step.tool_input, null, 2)}</pre>}</article>)}</div> : <pre className="py-3 whitespace-pre-wrap break-words text-xs">{typeof item === "string" ? item : JSON.stringify(item, null, 2)}</pre>}
    </div>}
  </section>;
}
