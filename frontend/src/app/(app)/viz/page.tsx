"use client";

import { useEffect, useState, type ReactNode } from "react";
import { SkeletonBlock } from "@/components/SkeletonStates";
import WikiGraph from "@/components/memory/WikiGraph";
import EmbeddingSpaceExplorer from "@/components/viz/EmbeddingSpaceExplorer";
import KnowledgeDensityMap from "@/components/viz/KnowledgeDensityMap";
import {
  getEmbeddingProjection,
  getKnowledgeDensity,
  getMemoryGraph,
  type WikiGraph as WikiGraphData,
} from "@/lib/api";
import type { EmbeddingProjection, KnowledgeDensity } from "@/lib/types";

/** Themes — every knowledge visualization in one place, full-width stacked
 *  cards. Each card fetches and renders independently so one slow endpoint
 *  can't hold the page. */
export default function VizPage() {
  const [graph, setGraph] = useState<WikiGraphData | null>(null);
  const [graphLoaded, setGraphLoaded] = useState(false);
  const [graphError, setGraphError] = useState<string | null>(null);
  const [projection, setProjection] = useState<EmbeddingProjection | null>(null);
  const [projectionLoaded, setProjectionLoaded] = useState(false);
  const [projectionError, setProjectionError] = useState<string | null>(null);
  const [density, setDensity] = useState<KnowledgeDensity | null>(null);
  const [densityLoaded, setDensityLoaded] = useState(false);
  const [densityError, setDensityError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    getMemoryGraph()
      .then((g) => { if (!cancelled) setGraph(g); })
      .catch((error) => { if (!cancelled) setGraphError(String(error)); })
      .finally(() => { if (!cancelled) setGraphLoaded(true); });
    getEmbeddingProjection(2000, "sessions")
      .then((p) => { if (!cancelled) setProjection(p); })
      .catch((error) => { if (!cancelled) setProjectionError(String(error)); })
      .finally(() => { if (!cancelled) setProjectionLoaded(true); });
    getKnowledgeDensity()
      .then((d) => { if (!cancelled) setDensity(d); })
      .catch((error) => { if (!cancelled) setDensityError(String(error)); })
      .finally(() => { if (!cancelled) setDensityLoaded(true); });
    return () => { cancelled = true; };
  }, []);

  return (
    <div
      className="h-full min-h-0 overflow-y-auto focus-visible:outline focus-visible:outline-2 focus-visible:outline-brand-400"
      tabIndex={0}
    >
      <div className="mx-auto max-w-[1100px] px-8 pb-10 pt-7">
        <h1 className="font-display text-[22px] font-semibold tracking-tight text-foreground">
          Themes
        </h1>
        <p className="mt-1 text-[12.5px] text-foreground/75">
          Themes and relationships across your sessions and memory.
        </p>

        <div className="mt-5 flex flex-col gap-5">
          <VizCard
            label="Session themes"
            description="Themes across your recent agent sessions. Each point is one session; nearby points began with similar user intent."
          >
            {!projectionLoaded ? (
              <SkeletonBlock className="h-[420px] w-full" />
            ) : projectionError ? (
              <VisualizationError message={projectionError} />
            ) : projection && projection.points.length > 0 ? (
              <div className="h-[420px]">
                <EmbeddingSpaceExplorer data={projection} />
              </div>
            ) : (
              <EmptyState height={180}>
                No session prompts have been embedded yet.
              </EmptyState>
            )}
          </VizCard>

          <VizCard
            label="Memory wiki"
            description="The curator's context graph — your wiki pages and the links between them. Click a node to open its page."
          >
            {!graphLoaded ? (
              <SkeletonBlock className="h-[560px] w-full" />
            ) : graphError ? (
              <VisualizationError message={graphError} />
            ) : graph && graph.nodes.length > 0 ? (
              <WikiGraph data={graph} />
            ) : (
              <EmptyState height={180}>
                No wiki pages yet. The Memory curator&apos;s nightly run compiles your
                history into a context graph of linked pages.
              </EmptyState>
            )}
          </VizCard>

          <VizCard
            label="Knowledge density"
            description="What your stash knows the most about — each block is a topic, sized by how much you have on it."
          >
            {!densityLoaded ? (
              <SkeletonBlock className="h-[320px] w-full" />
            ) : densityError ? (
              <VisualizationError message={densityError} />
            ) : density && density.clusters.length > 0 ? (
              <KnowledgeDensityMap data={density} />
            ) : (
              <EmptyState height={320}>
                No topics yet. Topics form as embedded content accumulates.
              </EmptyState>
            )}
          </VizCard>
        </div>
      </div>
    </div>
  );
}

function VizCard({
  label,
  description,
  children,
}: {
  label: string;
  description: string;
  children: ReactNode;
}) {
  return (
    <section>
      <div className="mb-1.5 flex flex-wrap items-baseline gap-x-3">
        <div className="font-mono text-[11.5px] font-medium text-foreground">{label}</div>
        <p className="text-[12px] text-foreground/75">{description}</p>
      </div>
      <div className="card-soft p-3">{children}</div>
    </section>
  );
}

function EmptyState({ height, children }: { height: number; children: ReactNode }) {
  return (
    <div
      className="flex items-center justify-center px-2 text-center text-[12.5px] text-foreground/75"
      style={{ height }}
    >
      {children}
    </div>
  );
}

function VisualizationError({ message }: { message: string }) {
  return (
    <div className="flex min-h-40 items-center justify-center px-6 text-center">
      <div>
        <p className="text-[12.5px] font-medium text-destructive">
          Couldn&apos;t load this visualization.
        </p>
        <p className="mt-1 max-w-xl text-[11px] text-muted-foreground">{message}</p>
      </div>
    </div>
  );
}
