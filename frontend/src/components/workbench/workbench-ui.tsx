"use client";

import { useCallback, useEffect, useState, type ReactNode } from "react";
import { Button } from "@/components/ui/button";
import { errorMessage } from "@/components/reward-models/rm-text";
import { cn } from "@/lib/utils";

export const inputClass = "w-full rounded-md border border-border bg-background px-3 py-2 text-[13px] text-foreground outline-none focus:border-brand-400 focus:ring-2 focus:ring-brand-400/20 disabled:opacity-50";

export function useWorkbenchLoad<T>(loader: () => Promise<T>, pollMs = 0) {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const load = useCallback(async () => {
    try { setData(await loader()); setError(null); }
    catch (e) { setError(errorMessage(e)); }
    finally { setLoading(false); }
  }, [loader]);
  useEffect(() => {
    let alive = true;
    const refresh = async () => {
      try { const next = await loader(); if (alive) { setData(next); setError(null); } }
      catch (e) { if (alive) setError(errorMessage(e)); }
      finally { if (alive) setLoading(false); }
    };
    void refresh();
    const timer = pollMs ? setInterval(() => { if (document.visibilityState === "visible") void refresh(); }, pollMs) : null;
    return () => { alive = false; if (timer) clearInterval(timer); };
  }, [loader, pollMs]);
  return { data, error, loading, reload: load };
}

export function ErrorNotice({ error, onRetry }: { error: string | null; onRetry?: () => void }) {
  if (!error) return null;
  return <div role="alert" className="mb-4 flex flex-wrap items-center justify-between gap-2 rounded-lg border border-red-500/20 bg-red-500/5 p-3 text-[13px] text-red-700 dark:text-red-400"><span>{error}</span>{onRetry && <Button size="sm" variant="outline" onClick={onRetry}>Retry</Button>}</div>;
}

export function RecordBadge({ value }: { value: string }) {
  return <span className={cn("inline-flex rounded-md px-2 py-0.5 text-[11px] font-medium", value === "failure" || value === "violates" || value === "failed" || value === "rejected" ? "bg-red-500/10 text-red-700 dark:text-red-400" : value === "success" || value === "meets" || value === "released" || value === "accepted" || value === "passed" ? "bg-emerald-500/10 text-emerald-700 dark:text-emerald-400" : "bg-surface text-muted-foreground")}>{value.replaceAll("_", " ")}</span>;
}

export function RecordPanel({ title, children, actions }: { title: ReactNode; children: ReactNode; actions?: ReactNode }) {
  return <section className="rounded-lg border border-border bg-background p-4"><div className="mb-3 flex flex-wrap items-start justify-between gap-2"><h2 className="m-0 text-[14px] font-medium">{title}</h2>{actions}</div>{children}</section>;
}

export function JsonDetails({ title, value, open = false }: { title: string; value: unknown; open?: boolean }) {
  return <details className="rounded-md border border-border-subtle p-3" open={open}><summary className="cursor-pointer text-[12px] font-medium text-dim">{title}</summary><pre className="m-0 mt-2 max-h-96 overflow-auto whitespace-pre-wrap break-words text-[11.5px] leading-relaxed text-muted-foreground">{typeof value === "string" ? value : JSON.stringify(value, null, 2) ?? "Not captured"}</pre></details>;
}
