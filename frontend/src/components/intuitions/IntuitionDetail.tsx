"use client";

import { useCallback, useEffect, useMemo, useRef, useState, type KeyboardEvent } from "react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useBreadcrumbs } from "@/components/BreadcrumbContext";
import { RmPageSkeleton } from "@/components/reward-models/RmSkeletons";
import { errorMessage } from "@/components/reward-models/rm-text";
import { cn } from "@/lib/utils";
import { imGet, type ModelDetail } from "@/lib/intuition-api";
import { workingVersion } from "./im-helpers";
import { IntuitionProvider, isTabId, LoadError, TABS, type IntuitionCtx, type TabId } from "./im-ui";
import IntuitionHeader from "./IntuitionHeader";
import PlaygroundTab from "./PlaygroundTab";
import VersionsTab from "./VersionsTab";

export default function IntuitionDetail({ id }: { id: string }) {
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const [detail, setDetail] = useState<ModelDetail | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);

  useBreadcrumbs(
    [{ label: "Reward models", href: "/reward-models/models" }, { label: detail?.model.name ?? "…" }],
    `im-${id}-${detail?.model.name ?? ""}`,
  );

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

  const goTo = useCallback(
    (tab: TabId, params: Record<string, string> = {}) => {
      const query = new URLSearchParams({ tab, ...params });
      router.replace(`${pathname}?${query.toString()}`, { scroll: false });
    },
    [router, pathname],
  );

  const ctx = useMemo<IntuitionCtx | null>(
    () =>
      detail && {
        id,
        detail,
        version: workingVersion(detail),
        apply: setDetail,
        reload,
        goTo,
      },
    [id, detail, reload, goTo],
  );

  if (loadError !== null && detail === null) {
    return (
      <div className="mx-auto max-w-6xl px-10 pt-7">
        <LoadError what="this reward model" message={loadError} onRetry={() => void reload()} />
      </div>
    );
  }
  if (!ctx) return <RmPageSkeleton />;

  const requested = searchParams.get("tab");
  const tab: TabId = isTabId(requested) ? requested : "playground";

  return (
    <IntuitionProvider value={ctx}>
      <div className="scroll-thin h-full overflow-y-auto">
        <div className="mx-auto max-w-6xl px-6 pt-5 pb-12">
          <IntuitionHeader />
          <TabBar tab={tab} onSelect={(t) => goTo(t)} />
          <div role="tabpanel" id={`im-panel-${tab}`} aria-labelledby={`im-tab-${tab}`} className={tab === "playground" ? "pt-0" : "pt-5"}>
            {tab === "playground" && <PlaygroundTab />}
            {tab === "versions" && <VersionsTab />}
          </div>
        </div>
      </div>
    </IntuitionProvider>
  );
}

function TabBar({ tab, onSelect }: { tab: TabId; onSelect: (tab: TabId) => void }) {
  const refs = useRef<Record<string, HTMLButtonElement | null>>({});

  function onKeyDown(e: KeyboardEvent) {
    const index = TABS.findIndex((t) => t.id === tab);
    const step = e.key === "ArrowRight" ? 1 : e.key === "ArrowLeft" ? -1 : 0;
    if (!step) return;
    e.preventDefault();
    const next = TABS[(index + step + TABS.length) % TABS.length].id;
    onSelect(next);
    refs.current[next]?.focus();
  }

  return (
    <div role="tablist" aria-label="Reward model sections" onKeyDown={onKeyDown} className="mt-5 flex gap-1 overflow-x-auto border-b border-border">
      {TABS.map((t) => {
        const selected = t.id === tab;
        return (
          <button
            key={t.id}
            ref={(el) => {
              refs.current[t.id] = el;
            }}
            id={`im-tab-${t.id}`}
            role="tab"
            type="button"
            aria-selected={selected}
            aria-controls={`im-panel-${t.id}`}
            tabIndex={selected ? 0 : -1}
            onClick={() => onSelect(t.id)}
            className={cn(
              "-mb-px inline-flex items-center gap-1.5 border-b-2 px-3 py-2 text-[13px] font-medium whitespace-nowrap transition-colors focus-visible:ring-2 focus-visible:ring-ring/50 focus-visible:outline-none",
              selected ? "border-brand-500 text-foreground" : "border-transparent text-muted-foreground hover:text-foreground",
            )}
          >
            {t.label}
          </button>
        );
      })}
    </div>
  );
}
