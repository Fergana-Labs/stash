"use client";

import { useEffect, useState, type ReactNode } from "react";
import { SkeletonBlock } from "@/components/SkeletonStates";
import EmbeddingSpaceExplorer from "@/components/viz/EmbeddingSpaceExplorer";
import KnowledgeDensityMap from "@/components/viz/KnowledgeDensityMap";
import WikiGraph from "@/components/memory/WikiGraph";
import {
  getEmbeddingProjection,
  getKnowledgeDensity,
  getMemoryGraph,
  type WikiGraph as WikiGraphData,
} from "@/lib/api";
import { cn } from "@/lib/utils";
import type { EmbeddingProjection, KnowledgeDensity } from "@/lib/types";

type View = "wiki" | "embeddings" | "topics";

const VIEWS: { key: View; label: string; blurb: string }[] = [
  { key: "wiki", label: "Memory wiki", blurb: "Curated pages and the links between them. Click a node to open its page." },
  { key: "embeddings", label: "Embedding space", blurb: "Every embedded page, table row, and session event, projected to 3D. Drag to rotate." },
  { key: "topics", label: "Knowledge map", blurb: "What your stash holds the most of. Area is volume, shade is recency." },
];

// Module-level so each panel's loader keeps its identity across renders and
// the fetch runs once per mounted view.
const loadWiki = () => getMemoryGraph();
const loadEmbeddings = () => getEmbeddingProjection(2000);
const loadTopics = () => getKnowledgeDensity();

function Centered({ children }: { children: ReactNode }) {
  return (
    <div className="flex h-[320px] items-center justify-center px-6 text-center text-[13px] text-muted-foreground">
      {children}
    </div>
  );
}

/** One visualization: fetches its data on mount, then hands it to `render`.
 *  Each view mounts only while its tab is selected. */
function VizPanel<T>({
  load,
  isEmpty,
  emptyMessage,
  render,
}: {
  load: () => Promise<T>;
  isEmpty: (data: T) => boolean;
  emptyMessage: string;
  render: (data: T) => ReactNode;
}) {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    load()
      .then((loaded) => {
        if (!cancelled) setData(loaded);
      })
      .catch((e) => {
        if (!cancelled) setError(e instanceof Error ? e.message : String(e));
      });
    return () => {
      cancelled = true;
    };
  }, [load]);

  if (error) return <Centered>Couldn&apos;t load this view: {error}</Centered>;
  if (!data) return <SkeletonBlock className="h-[420px] w-full" />;
  if (isEmpty(data)) return <Centered>{emptyMessage}</Centered>;
  return <>{render(data)}</>;
}

/** The Visualizations section — the three views of the stash's shape, which
 *  used to be cards on Home. One at a time, each with the full canvas. */
export default function VisualizationsPage() {
  const [view, setView] = useState<View>("wiki");
  const active = VIEWS.find((v) => v.key === view)!;

  return (
    <div className="h-full overflow-y-auto">
      <div className="mx-auto max-w-[1360px] px-8 pb-10 pt-7">
        <h1 className="font-display text-[22px] font-semibold tracking-tight text-foreground">
          Visualizations
        </h1>

        <div role="tablist" aria-label="Visualizations" className="mt-4 flex gap-1 border-b border-border">
          {VIEWS.map((v) => (
            <button
              key={v.key}
              role="tab"
              aria-selected={v.key === view}
              onClick={() => setView(v.key)}
              className={cn(
                "-mb-px border-b-2 px-3 pb-2 pt-1 text-[13px] font-medium transition-colors",
                v.key === view
                  ? "border-brand-500 text-foreground"
                  : "border-transparent text-muted-foreground hover:text-foreground",
              )}
            >
              {v.label}
            </button>
          ))}
        </div>

        <p className="mt-2.5 text-[13px] text-muted-foreground">{active.blurb}</p>

        <div className="card-soft mt-3 p-3">
          {view === "wiki" && (
            <VizPanel<WikiGraphData>
              load={loadWiki}
              isEmpty={(d) => d.nodes.length === 0}
              emptyMessage="No wiki pages yet. The Memory curator's nightly run compiles your history into a context graph of linked pages."
              render={(d) => <WikiGraph data={d} />}
            />
          )}

          {view === "embeddings" && (
            <VizPanel<EmbeddingProjection>
              load={loadEmbeddings}
              isEmpty={(d) => d.points.length === 0}
              emptyMessage="No embeddings indexed yet. Pages, table rows, and session events get embedded as they're added."
              render={(d) => (
                <div className="h-[560px]">
                  <EmbeddingSpaceExplorer data={d} />
                </div>
              )}
            />
          )}

          {view === "topics" && (
            <VizPanel<KnowledgeDensity>
              load={loadTopics}
              isEmpty={(d) => d.clusters.length === 0}
              emptyMessage="Nothing to cluster yet. Topics appear once your stash has enough embedded content."
              render={(d) => <KnowledgeDensityMap data={d} />}
            />
          )}
        </div>
      </div>
    </div>
  );
}
