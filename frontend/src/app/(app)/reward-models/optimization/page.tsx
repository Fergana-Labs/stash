"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { useSearchParams } from "next/navigation";
import { useBreadcrumbs } from "@/components/BreadcrumbContext";
import { RmPage } from "@/components/reward-models/rm-ui";
import { Button } from "@/components/ui/button";
import CreateOptimization from "@/components/optimization/CreateOptimization";
import { listOptimizations, type Optimization } from "@/lib/optimization-api";
import { errorMessage } from "@/components/reward-models/rm-text";

export default function OptimizationPage() {
  const params = useSearchParams();
  const initialModelId = params.get("model") ?? "";
  const [programs, setPrograms] = useState<Optimization[] | null>(null);
  const [creating, setCreating] = useState(!!initialModelId || params.has("new"));
  const [error, setError] = useState<string | null>(null);
  useBreadcrumbs([{ label: "Optimization" }], "optimization");
  useEffect(() => { let live = true; void listOptimizations().then((rows) => { if (live) setPrograms(rows); }).catch((e) => { if (live) setError(errorMessage(e)); }); return () => { live = false; }; }, []);
  return <RmPage title="Optimization" description="Turn feedback into better instructions. Follow reward and business results as your agent works." actions={programs?.length ? <Button onClick={() => setCreating(!creating)}>{creating ? "Back to optimizations" : "Begin prompt optimization"}</Button> : undefined}>
    {error && <p role="alert" className="text-sm text-red-600">{error}</p>}
    {creating || programs?.length === 0 ? <CreateOptimization initialModelId={initialModelId} /> : programs === null ? <p className="text-sm text-muted-foreground">Loading optimizations…</p> : <div className="grid gap-4 md:grid-cols-2">{programs.map((p) => <Link key={p.id} href={`/reward-models/optimization/${p.id}`} className="rounded-xl border border-border p-5 transition-colors hover:border-foreground/30"><div className="flex items-center justify-between gap-4"><h2 className="m-0 text-base font-medium">{p.name}</h2><span className="rounded bg-surface px-2 py-1 text-xs">{p.status.replaceAll("_", " ")}</span></div><p className="text-sm text-muted-foreground">{p.agent} · {p.scope}</p><div className="flex flex-wrap gap-4 text-xs text-muted-foreground"><span>{p.run_count ?? 0} runs</span><span>{p.metric.name} · {p.metric.direction} is better</span></div>{p.error && <p className="mb-0 text-xs text-red-600">{p.error}</p>}</Link>)}</div>}
  </RmPage>;
}
