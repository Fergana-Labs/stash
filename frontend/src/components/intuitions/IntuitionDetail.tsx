"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { useBreadcrumbs } from "@/components/BreadcrumbContext";
import { RmPageSkeleton } from "@/components/reward-models/RmSkeletons";
import { errorMessage } from "@/components/reward-models/rm-text";
import { imGet, type ModelDetail } from "@/lib/intuition-api";
import { workingVersion } from "./im-helpers";
import { IntuitionProvider, LoadError, type IntuitionCtx } from "./im-ui";
import IntuitionHeader from "./IntuitionHeader";
import PlaygroundTab from "./PlaygroundTab";

function ModelBreadcrumbs({ id, name }: { id: string; name: string }) {
  useBreadcrumbs([{ label: "Reward models", href: "/reward-models/models" }, { label: name }], `im-${id}-${name}`);
  return null;
}

export default function IntuitionDetail({ id, embedded = false }: { id: string; embedded?: boolean }) {
  const [detail, setDetail] = useState<ModelDetail | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);

  const reload = useCallback(async () => {
    try {
      setDetail(await imGet(id));
      setLoadError(null);
    } catch (e) {
      setLoadError(errorMessage(e));
    }
  }, [id]);

  useEffect(() => {
    void reload();
  }, [reload]);

  const ctx = useMemo<IntuitionCtx | null>(
    () =>
      detail && {
        id,
        detail,
        version: workingVersion(detail),
        apply: setDetail,
        reload,
      },
    [id, detail, reload],
  );

  if (loadError !== null && detail === null) {
    return (
      <div className={embedded ? "px-5 py-3" : "mx-auto max-w-6xl px-10 pt-7"}>
        <LoadError what="this reward model" message={loadError} onRetry={() => void reload()} />
      </div>
    );
  }
  if (!ctx) return <RmPageSkeleton />;

  if (embedded) return <IntuitionProvider value={ctx}><PlaygroundTab embedded /></IntuitionProvider>;

  return (
    <IntuitionProvider value={ctx}>
      <ModelBreadcrumbs id={id} name={detail?.model.name ?? "…"} />
      <div className="scroll-thin h-full overflow-y-auto">
        <div className="mx-auto max-w-6xl px-6 pt-5 pb-12">
          <IntuitionHeader />
          <div className="mt-4 border-t border-border">
            <PlaygroundTab />
          </div>
        </div>
      </div>
    </IntuitionProvider>
  );
}
