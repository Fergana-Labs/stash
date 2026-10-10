"use client";

import { useCallback, useEffect, useMemo, useRef, useState, type KeyboardEvent } from "react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useBreadcrumbs } from "@/components/BreadcrumbContext";
import { RmPageSkeleton } from "@/components/reward-models/RmSkeletons";
import { errorMessage } from "@/components/reward-models/rm-text";
import { cn } from "@/lib/utils";
import { imExamples, imGet, type Example, type ModelDetail } from "@/lib/intuition-api";
import { workingVersion } from "./im-helpers";
import { IntuitionProvider, isTabId, LoadError, TABS, type IntuitionCtx, type TabId } from "./im-ui";
import IntuitionHeader from "./IntuitionHeader";
import PlaygroundTab from "./PlaygroundTab";
import InboxTab from "./InboxTab";
import ExamplesTab from "./ExamplesTab";
import RubricTab from "./RubricTab";
import TrainTab from "./TrainTab";
import VersionsTab from "./VersionsTab";

export default function IntuitionDetail({ id }: { id: string }) {
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const [detail, setDetail] = useState<ModelDetail | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [examples, setExamples] = useState<Example[] | null>(null);
  const [examplesError, setExamplesError] = useState<string | null>(null);

  useBreadcrumbs(
    [{ label: "Reward models", href: "/reward-models" }, { label: "Intuitions", href: "/reward-models/intuitions" }, { label: detail?.model.name ?? "…" }],
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

  const reloadExamples = useCallback(async () => {
    try {
      setExamples(await imExamples(id));
      setExamplesError(null);
    } catch (e) {
      setExamplesError(errorMessage(e));
    }
  }, [id]);

  useEffect(() => {
    void reload();
    void reloadExamples();
  }, [reload, reloadExamples]);

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
        examples,
        examplesError,
        setExamples,
        reloadExamples,
        goTo,
      },
    [id, detail, reload, examples, examplesError, reloadExamples, goTo],
  );

  if (loadError !== null && detail === null) {
    return (
      <div className="mx-auto max-w-6xl px-10 pt-7">
        <LoadError what="this intuition model" message={loadError} onRetry={() => void reload()} />
      </div>
    );
  }
  if (!ctx) return <RmPageSkeleton />;

  const requested = searchParams.get("tab");
  const hasRubric = (ctx.version?.rubric.length ?? 0) > 0;
  const tab: TabId = isTabId(requested) ? requested : hasRubric ? "playground" : "rubric";

  return (
    <IntuitionProvider value={ctx}>
      <div className="scroll-thin h-full overflow-y-auto">
        <div className="mx-auto max-w-6xl px-10 pt-6 pb-16">
          <IntuitionHeader />
          <TabBar tab={tab} detail={ctx.detail} examples={examples} onSelect={(t) => goTo(t)} />
          <div role="tabpanel" id={`im-panel-${tab}`} aria-labelledby={`im-tab-${tab}`} className="pt-5">
            {tab === "playground" && <PlaygroundTab />}
            {tab === "inbox" && <InboxTab />}
            {tab === "examples" && <ExamplesTab />}
            {tab === "rubric" && <RubricTab />}
            {tab === "train" && <TrainTab />}
            {tab === "versions" && <VersionsTab />}
          </div>
        </div>
      </div>
    </IntuitionProvider>
  );
}

function TabBar({ tab, detail, examples, onSelect }: { tab: TabId; detail: ModelDetail; examples: Example[] | null; onSelect: (tab: TabId) => void }) {
  const refs = useRef<Record<string, HTMLButtonElement | null>>({});
  const needsReview = examples?.filter((e) => e.needs_review).length ?? detail.counts.needs_review;
  const counts: Partial<Record<TabId, { n: number; strong?: boolean; title: string }>> = {
    inbox: detail.counts.inbox ? { n: detail.counts.inbox, strong: true, title: "Unreviewed predictions" } : undefined,
    examples: { n: examples?.length ?? detail.counts.total, strong: needsReview > 0, title: needsReview ? `${needsReview} need review` : "Examples" },
    train: detail.counts.ungraded_total ? { n: detail.counts.ungraded_total, title: "Ungraded items" } : undefined,
  };

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
    <div role="tablist" aria-label="Intuition model sections" onKeyDown={onKeyDown} className="mt-5 flex gap-1 overflow-x-auto border-b border-border">
      {TABS.map((t) => {
        const count = counts[t.id];
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
            {count && (
              <span
                title={count.title}
                className={cn("rounded-full px-1.5 font-mono text-[10.5px] tabular-nums", count.strong ? "bg-brand-500/12 text-brand-600" : "bg-raised text-muted-foreground")}
              >
                {count.n}
              </span>
            )}
          </button>
        );
      })}
    </div>
  );
}
