"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { ArrowLeft } from "lucide-react";
import { useBreadcrumbs } from "@/components/BreadcrumbContext";
import { Button } from "@/components/ui/button";
import { rmGetRewardModel } from "@/lib/api";
import type { RmRewardModelDetail } from "@/lib/types";
import { errorMessage } from "./rm-text";
import { isActiveJob } from "./rm-ui";
import CustomModelTraceSandbox from "./CustomModelTraceSandbox";

export default function ModelPlayground({ modelId }: { modelId: string }) {
  const [model, setModel] = useState<RmRewardModelDetail | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [reload, setReload] = useState(0);
  useBreadcrumbs([{ label: "Reward models", href: "/reward-models/models" }, { label: model?.name ?? "Model" }], "rm-playground");

  useEffect(() => {
    let cancelled = false;
    let timer: ReturnType<typeof setTimeout>;
    async function load() {
      try {
        const result = await rmGetRewardModel(modelId);
        if (cancelled) return;
        setModel(result); setLoadError(null);
        if (isActiveJob(result.status)) timer = setTimeout(() => void load(), 3000);
      } catch (e) { if (!cancelled) setLoadError(errorMessage(e)); }
    }
    void load();
    return () => { cancelled = true; clearTimeout(timer); };
  }, [modelId, reload]);

  const current = model?.id === modelId ? model : null;
  return <div className="scroll-thin h-full overflow-y-auto">
    <div className="mx-auto max-w-6xl px-6 pt-5 pb-12">
      <header>
        <Link href="/reward-models/models" className="inline-flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground">
          <ArrowLeft className="h-3.5 w-3.5" />Reward models
        </Link>
        <div className="mt-2 flex flex-wrap items-center justify-between gap-3">
          <h1 className="m-0 truncate font-display text-lg font-semibold tracking-tight">{current?.name ?? "Reward model"}</h1>
          {current && <Link className="text-xs text-muted-foreground underline decoration-border underline-offset-4 hover:text-foreground" href={"/reward-models?selected=" + current.trace_ids.join(",")}>{current.trace_count} training traces</Link>}
        </div>
      </header>
      {loadError ? <div role="alert" className="py-5 text-sm text-destructive">
        <p>{loadError}</p>
        <Button variant="outline" size="sm" className="mt-2" onClick={() => setReload((value) => value + 1)}>Try again</Button>
      </div> : current ? <CustomModelTraceSandbox key={current.id} model={current} /> : <p role="status" className="py-5 text-xs text-muted-foreground">Loading model…</p>}
    </div>
  </div>;
}
