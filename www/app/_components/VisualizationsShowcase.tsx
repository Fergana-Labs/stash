import type { CSSProperties } from "react";

const SOURCE_COLORS: Record<string, string> = {
  history: "#8B5CF6",
  notebook: "#22C55E",
  table: "#3B82F6",
};

type EmbedPoint = {
  x: number;
  y: number;
  depth: number;
  source: "history" | "notebook" | "table";
  label: string;
};

// Hand-curated mock points for the "memory_reading_store" workspace embedding
// projection. Positions are chosen to look like a 3D point cloud with clusters
// per resource type (history/notebooks/tables). Values are fixed, not random,
// so rendering is deterministic across SSR and client.
const EMBEDDING_POINTS: EmbedPoint[] = [
  // History cluster (violet) — bottom-left-ish
  { x: 82, y: 220, depth: 0.25, source: "history", label: "rex:query-optim" },
  { x: 98, y: 198, depth: 0.4, source: "history", label: "scout:pgvector-seed" },
  { x: 110, y: 232, depth: 0.18, source: "history", label: "rex:vector-dim" },
  { x: 126, y: 208, depth: 0.55, source: "history", label: "nova:index-tune" },
  { x: 140, y: 245, depth: 0.22, source: "history", label: "rex:hnsw-build" },
  { x: 155, y: 220, depth: 0.35, source: "history", label: "scout:ef-search" },
  { x: 170, y: 252, depth: 0.45, source: "history", label: "rex:bench-recall" },
  { x: 186, y: 228, depth: 0.3, source: "history", label: "nova:cosine-vs-l2" },
  { x: 200, y: 260, depth: 0.5, source: "history", label: "rex:backfill" },
  { x: 215, y: 238, depth: 0.25, source: "history", label: "scout:chunk-size" },
  { x: 112, y: 270, depth: 0.6, source: "history", label: "ari:embed-cost" },
  { x: 148, y: 282, depth: 0.4, source: "history", label: "rex:ivfflat-try" },
  { x: 178, y: 290, depth: 0.3, source: "history", label: "scout:rerank-loop" },
  { x: 92, y: 252, depth: 0.5, source: "history", label: "nova:warm-cache" },
  { x: 164, y: 196, depth: 0.7, source: "history", label: "rex:token-limit" },

  // Notebooks cluster (green) — center-right
  { x: 320, y: 140, depth: 0.7, source: "notebook", label: "pgvector-howto" },
  { x: 342, y: 128, depth: 0.6, source: "notebook", label: "embedding-models" },
  { x: 360, y: 158, depth: 0.8, source: "notebook", label: "hnsw-vs-ivfflat" },
  { x: 378, y: 142, depth: 0.5, source: "notebook", label: "chunking-strategy" },
  { x: 395, y: 168, depth: 0.75, source: "notebook", label: "rerank-patterns" },
  { x: 335, y: 172, depth: 0.45, source: "notebook", label: "recall-at-k" },
  { x: 358, y: 188, depth: 0.65, source: "notebook", label: "cost-per-1k" },
  { x: 382, y: 200, depth: 0.55, source: "notebook", label: "filter-push-down" },
  { x: 405, y: 138, depth: 0.85, source: "notebook", label: "reading-store-arch" },
  { x: 418, y: 172, depth: 0.7, source: "notebook", label: "sleep-time-curation" },
  { x: 350, y: 112, depth: 0.9, source: "notebook", label: "index-playbook" },
  { x: 372, y: 220, depth: 0.4, source: "notebook", label: "eval-harness" },

  // Tables cluster (blue) — top-right
  { x: 440, y: 80, depth: 0.95, source: "table", label: "books.csv" },
  { x: 462, y: 95, depth: 0.85, source: "table", label: "articles.jsonl" },
  { x: 480, y: 72, depth: 1, source: "table", label: "authors.csv" },
  { x: 498, y: 108, depth: 0.8, source: "table", label: "tags.parquet" },
  { x: 515, y: 88, depth: 0.9, source: "table", label: "sessions.csv" },
  { x: 455, y: 118, depth: 0.75, source: "table", label: "highlights.jsonl" },
  { x: 478, y: 132, depth: 0.7, source: "table", label: "ratings.csv" },
  { x: 502, y: 142, depth: 0.65, source: "table", label: "embeddings.parquet" },

  // A few outliers bridging clusters (show graph topology)
  { x: 260, y: 188, depth: 0.5, source: "history", label: "bridge:search-loop" },
  { x: 285, y: 160, depth: 0.6, source: "notebook", label: "bridge:query-planner" },
  { x: 420, y: 118, depth: 0.75, source: "notebook", label: "bridge:schema-dx" },
];

function EmbeddingProjectionMock() {
  const width = 600;
  const height = 360;
  return (
    <div
      className="relative overflow-hidden rounded-[14px] border border-border bg-background"
      style={{ boxShadow: "var(--shadow-card)" }}
    >
      <div className="flex items-center justify-between border-b border-border-subtle bg-surface px-4 py-3">
        <div className="flex items-center gap-2.5">
          <span className="h-2 w-2 rounded-full bg-[#8B5CF6]" />
          <span className="text-[13px] font-semibold text-ink">
            embedding projection
          </span>
          <span className="font-mono text-[11px] text-muted">
            memory_reading_store
          </span>
        </div>
        <span className="font-mono text-[10px] uppercase tracking-[0.12em] text-dim">
          38 / 1,284 points
        </span>
      </div>
      <div className="relative aspect-[600/360] w-full">
        <svg
          viewBox={`0 0 ${width} ${height}`}
          className="absolute inset-0 h-full w-full"
          role="img"
          aria-label="3D embedding projection"
        >
          <defs>
            <pattern
              id="embed-grid"
              width="40"
              height="40"
              patternUnits="userSpaceOnUse"
            >
              <path
                d="M 40 0 L 0 0 0 40"
                fill="none"
                stroke="rgba(15,23,42,0.04)"
                strokeWidth="1"
              />
            </pattern>
            <radialGradient id="embed-glow" cx="50%" cy="50%" r="50%">
              <stop offset="0%" stopColor="rgba(249,115,22,0.06)" />
              <stop offset="100%" stopColor="rgba(249,115,22,0)" />
            </radialGradient>
          </defs>
          <rect width={width} height={height} fill="url(#embed-grid)" />
          <rect width={width} height={height} fill="url(#embed-glow)" />

          {/* Subtle axes */}
          <g stroke="rgba(15,23,42,0.12)" strokeWidth="1">
            <line x1="60" y1="310" x2="560" y2="310" />
            <line x1="60" y1="310" x2="60" y2="40" />
            <line x1="60" y1="310" x2="180" y2="220" strokeDasharray="3 3" />
          </g>
          <g
            fill="rgba(15,23,42,0.35)"
            fontFamily="ui-monospace, Menlo, monospace"
            fontSize="9"
          >
            <text x="545" y="324">PC1</text>
            <text x="40" y="48">PC2</text>
            <text x="184" y="215">PC3</text>
          </g>

          {EMBEDDING_POINTS.map((p, i) => {
            const color = SOURCE_COLORS[p.source];
            const r = 3 + p.depth * 3.5;
            const opacity = 0.45 + p.depth * 0.55;
            return (
              <circle
                key={i}
                cx={p.x}
                cy={p.y}
                r={r}
                fill={color}
                opacity={opacity}
              />
            );
          })}
        </svg>

        {/* Legend */}
        <div className="absolute bottom-3 left-3 flex flex-col gap-1 rounded-md border border-border-subtle bg-background/85 px-2.5 py-2 backdrop-blur">
          {[
            { src: "history", label: "History" },
            { src: "notebook", label: "Notebooks" },
            { src: "table", label: "Tables" },
          ].map((row) => (
            <div
              key={row.src}
              className="flex items-center gap-2 font-mono text-[10.5px] text-dim"
            >
              <span
                className="h-[7px] w-[7px] rounded-full"
                style={{ background: SOURCE_COLORS[row.src] }}
              />
              {row.label}
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

type GraphNode = {
  id: string;
  x: number;
  y: number;
  degree: number;
};

// Wiki page graph for "memory_reading_store". Positions are hand-chosen to
// resemble a force-directed layout; degree drives node size + color.
const GRAPH_NODES: GraphNode[] = [
  { id: "pgvector-howto", x: 295, y: 170, degree: 7 },
  { id: "reading-store-arch", x: 180, y: 100, degree: 6 },
  { id: "hnsw-vs-ivfflat", x: 400, y: 110, degree: 5 },
  { id: "chunking-strategy", x: 420, y: 220, degree: 4 },
  { id: "rerank-patterns", x: 300, y: 270, degree: 4 },
  { id: "recall-at-k", x: 180, y: 230, degree: 3 },
  { id: "embedding-models", x: 70, y: 150, degree: 3 },
  { id: "cost-per-1k", x: 100, y: 300, degree: 2 },
  { id: "eval-harness", x: 220, y: 310, degree: 2 },
  { id: "sleep-time-curation", x: 500, y: 300, degree: 1 },
  { id: "index-playbook", x: 510, y: 60, degree: 1 },
  { id: "filter-push-down", x: 520, y: 165, degree: 1 },
];

const GRAPH_EDGES: Array<[string, string]> = [
  ["pgvector-howto", "reading-store-arch"],
  ["pgvector-howto", "hnsw-vs-ivfflat"],
  ["pgvector-howto", "chunking-strategy"],
  ["pgvector-howto", "rerank-patterns"],
  ["pgvector-howto", "recall-at-k"],
  ["pgvector-howto", "embedding-models"],
  ["pgvector-howto", "filter-push-down"],
  ["reading-store-arch", "embedding-models"],
  ["reading-store-arch", "hnsw-vs-ivfflat"],
  ["reading-store-arch", "index-playbook"],
  ["reading-store-arch", "cost-per-1k"],
  ["hnsw-vs-ivfflat", "chunking-strategy"],
  ["hnsw-vs-ivfflat", "recall-at-k"],
  ["chunking-strategy", "rerank-patterns"],
  ["chunking-strategy", "eval-harness"],
  ["rerank-patterns", "eval-harness"],
  ["rerank-patterns", "sleep-time-curation"],
  ["recall-at-k", "eval-harness"],
  ["embedding-models", "cost-per-1k"],
];

function PageGraphMock() {
  const width = 600;
  const height = 360;
  const nodeById = new Map(GRAPH_NODES.map((n) => [n.id, n]));

  const nodeColor = (degree: number) => {
    if (degree >= 5) return "#F97316";
    if (degree >= 3) return "#EA7C1F";
    if (degree === 0) return "#8B5CF6";
    return "#64748B";
  };

  return (
    <div
      className="relative overflow-hidden rounded-[14px] border border-border bg-background"
      style={{ boxShadow: "var(--shadow-card)" }}
    >
      <div className="flex items-center justify-between border-b border-border-subtle bg-surface px-4 py-3">
        <div className="flex items-center gap-2.5">
          <span className="h-2 w-2 rounded-full bg-brand" />
          <span className="text-[13px] font-semibold text-ink">page graph</span>
          <span className="font-mono text-[11px] text-muted">
            wiki · reading-store
          </span>
        </div>
        <span className="font-mono text-[10px] uppercase tracking-[0.12em] text-dim">
          12 pages · 19 backlinks
        </span>
      </div>
      <div className="relative aspect-[600/360] w-full">
        <svg
          viewBox={`0 0 ${width} ${height}`}
          className="absolute inset-0 h-full w-full"
          role="img"
          aria-label="Wiki page graph"
        >
          <defs>
            <pattern
              id="graph-grid"
              width="40"
              height="40"
              patternUnits="userSpaceOnUse"
            >
              <path
                d="M 40 0 L 0 0 0 40"
                fill="none"
                stroke="rgba(15,23,42,0.04)"
                strokeWidth="1"
              />
            </pattern>
          </defs>
          <rect width={width} height={height} fill="url(#graph-grid)" />

          {/* Edges */}
          <g stroke="rgba(15,23,42,0.22)" strokeWidth="1">
            {GRAPH_EDGES.map(([a, b], i) => {
              const na = nodeById.get(a);
              const nb = nodeById.get(b);
              if (!na || !nb) return null;
              return <line key={i} x1={na.x} y1={na.y} x2={nb.x} y2={nb.y} />;
            })}
          </g>

          {/* Nodes */}
          {GRAPH_NODES.map((n) => {
            const r = 6 + n.degree * 1.2;
            const fill = nodeColor(n.degree);
            return (
              <g key={n.id}>
                <circle
                  cx={n.x}
                  cy={n.y}
                  r={r}
                  fill={fill}
                  stroke="white"
                  strokeWidth="1.5"
                />
                <text
                  x={n.x + r + 4}
                  y={n.y + 3}
                  fontFamily="ui-monospace, Menlo, monospace"
                  fontSize="9.5"
                  fill="rgba(15,23,42,0.62)"
                >
                  {n.id}
                </text>
              </g>
            );
          })}
        </svg>

        {/* Legend */}
        <div className="absolute bottom-3 right-3 flex flex-col gap-1 rounded-md border border-border-subtle bg-background/85 px-2.5 py-2 backdrop-blur">
          {[
            { dot: "#F97316", label: "hub" },
            { dot: "#64748B", label: "leaf" },
          ].map((row) => (
            <div
              key={row.label}
              className="flex items-center gap-2 font-mono text-[10.5px] text-dim"
            >
              <span
                className="h-[7px] w-[7px] rounded-full"
                style={{ background: row.dot } as CSSProperties}
              />
              {row.label}
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

function EyebrowDot({ children }: { children: React.ReactNode }) {
  return (
    <p className="flex items-center font-mono text-[11px] font-medium uppercase tracking-[0.14em] text-muted">
      <span className="mr-[10px] inline-block h-[6px] w-[6px] rounded-full bg-brand" />
      {children}
    </p>
  );
}

export default function VisualizationsShowcase() {
  return (
    <section
      id="visualizations"
      className="border-b border-border-subtle py-24 md:py-32"
    >
      <div className="mx-auto max-w-[1200px] px-7">
        <div className="flex max-w-[880px] flex-col gap-4">
          <EyebrowDot>See the memory form</EyebrowDot>
          <h2 className="font-display text-[clamp(32px,4.2vw,52px)] font-bold leading-[1.05] tracking-[-0.03em] text-ink text-balance">
            Your team&apos;s brain,
            <br />
            <span className="font-medium text-dim">actually visible.</span>
          </h2>
          <p className="max-w-[620px] text-[17px] leading-[1.55] text-dim">
            Every session, page, and table gets embedded into one space. Stash
            plots them so you can see how your team&apos;s knowledge clusters,
            and which pages have become hubs the graph leans on.
          </p>
        </div>
        <div className="mt-12 grid grid-cols-1 gap-5 lg:grid-cols-2">
          <div>
            <EmbeddingProjectionMock />
            <p className="mt-4 text-[13.5px] leading-[1.6] text-dim">
              <span className="text-ink">3D embedding projection.</span> History
              events, notebooks, and tables projected with PCA. Clusters form
              around topics — not folders.
            </p>
          </div>
          <div>
            <PageGraphMock />
            <p className="mt-4 text-[13.5px] leading-[1.6] text-dim">
              <span className="text-ink">Wiki page graph.</span> Nodes are
              pages, edges are <span className="font-mono text-brand">[[backlinks]]</span>.
              Orange nodes are the hubs your agents keep citing.
            </p>
          </div>
        </div>
      </div>
    </section>
  );
}
