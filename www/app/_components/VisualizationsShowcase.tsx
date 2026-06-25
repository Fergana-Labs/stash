import type { CSSProperties } from "react";

import EmbeddingProjection3D from "./EmbeddingProjection3D";

type GraphNode = {
  id: string;
  x: number;
  y: number;
  degree: number;
};

// Curated wiki graph for "reading-store". Positions are hand-chosen to
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
  { id: "release-notes", x: 500, y: 300, degree: 1 },
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
  ["rerank-patterns", "release-notes"],
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
    if (degree === 0) return "#F97316";
    return "#6B655B";
  };

  return (
    <div
      className="relative overflow-hidden rounded-[14px] border border-border bg-background"
      style={{ boxShadow: "var(--shadow-card)" }}
    >
      <div className="flex items-center justify-between border-b border-border-subtle bg-surface px-4 py-3">
        <div className="flex items-center gap-2.5">
          <span className="h-2 w-2 rounded-full bg-brand" />
          <span className="text-[13px] font-semibold text-ink">Wiki</span>
        </div>
        <span className="font-mono text-[10px] uppercase tracking-[0.12em] text-dim">
          12 pages · 19 links
        </span>
      </div>
      <div className="relative aspect-[600/360] w-full">
        <svg
          viewBox={`0 0 ${width} ${height}`}
          className="absolute inset-0 h-full w-full"
          role="img"
          aria-label="Curated wiki graph"
        >
          <defs>
            <pattern
              id="tree-grid"
              width="40"
              height="40"
              patternUnits="userSpaceOnUse"
            >
              <path
                d="M 40 0 L 0 0 0 40"
                fill="none"
                stroke="rgba(26,23,20,0.04)"
                strokeWidth="1"
              />
            </pattern>
          </defs>
          <rect width={width} height={height} fill="url(#tree-grid)" />

          <g stroke="rgba(26,23,20,0.22)" strokeWidth="1">
            {GRAPH_EDGES.map(([a, b], i) => {
              const na = nodeById.get(a);
              const nb = nodeById.get(b);
              if (!na || !nb) return null;
              return <line key={i} x1={na.x} y1={na.y} x2={nb.x} y2={nb.y} />;
            })}
          </g>

          {GRAPH_NODES.map((n) => {
            const r = 6 + n.degree * 1.2;
            const fill = nodeColor(n.degree);
            // Right-edge labels flip to the left side so they don't clip.
            const labelLeft = n.x > 450;
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
                  x={labelLeft ? n.x - r - 4 : n.x + r + 4}
                  y={n.y + 3}
                  textAnchor={labelLeft ? "end" : "start"}
                  fontFamily="ui-monospace, Menlo, monospace"
                  fontSize="12"
                  fill="rgba(26,23,20,0.62)"
                >
                  {n.id}
                </text>
              </g>
            );
          })}
        </svg>

        <div className="absolute bottom-3 right-3 flex flex-col gap-1 rounded-md border border-border-subtle bg-background/85 px-2.5 py-2 backdrop-blur">
          {[
            { dot: "#F97316", label: "hub" },
            { dot: "#6B655B", label: "leaf" },
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

const GREP_MATCHES = [
  { file: "pgvector-howto.md", line: 42, before: "set hnsw.", after: " = 80;" },
  { file: "reading-store-arch.md", line: 118, before: "tune ", after: " per query" },
  { file: "eval-harness.md", line: 9, before: "sweep ", after: " {40, 80, 160}" },
];

function GrepSearchMock() {
  return (
    <div
      className="relative overflow-hidden rounded-[14px] border border-border bg-background"
      style={{ boxShadow: "var(--shadow-card)" }}
    >
      <div className="flex items-center justify-between border-b border-border-subtle bg-surface px-4 py-3">
        <div className="flex items-center gap-2.5">
          <span className="h-2 w-2 rounded-full bg-brand" />
          <span className="text-[13px] font-semibold text-ink">Grep</span>
        </div>
        <span className="font-mono text-[10px] uppercase tracking-[0.12em] text-dim">
          3 matches · 38 ms
        </span>
      </div>
      <div className="relative aspect-[600/360] w-full">
        <svg className="absolute inset-0 h-full w-full" aria-hidden="true">
          <defs>
            <pattern
              id="grep-grid"
              width="40"
              height="40"
              patternUnits="userSpaceOnUse"
            >
              <path
                d="M 40 0 L 0 0 0 40"
                fill="none"
                stroke="rgba(26,23,20,0.04)"
                strokeWidth="1"
              />
            </pattern>
          </defs>
          <rect width="100%" height="100%" fill="url(#grep-grid)" />
        </svg>
        <div className="absolute inset-0 flex flex-col gap-2 overflow-hidden p-5 font-mono text-[12px] leading-[1.5]">
          <div className="whitespace-nowrap text-dim">
            <span className="text-muted">$ </span>
            <span className="text-ink">grep -rn &quot;ef_search&quot; .</span>
          </div>
          {GREP_MATCHES.map((m) => (
            <div key={m.file} className="truncate text-dim">
              <span className="text-muted">
                {m.file}:{m.line}:
              </span>
              {m.before}
              <span className="font-semibold text-brand">ef_search</span>
              {m.after}
            </div>
          ))}
          <div className="whitespace-nowrap text-muted">
            3 matches in 12 files (0.04s)
          </div>
          <div className="whitespace-nowrap text-dim">
            <span className="text-muted">$ </span>
            <span className="animate-pulse text-ink">▌</span>
          </div>
        </div>
      </div>
    </div>
  );
}

function EyebrowDot({ children }: { children: React.ReactNode }) {
  return <p className="kicker">{children}</p>;
}

export default function VisualizationsShowcase() {
  return (
    <section
      id="visualizations"
      className="border-b border-border-subtle py-24 md:py-32"
    >
      <div className="mx-auto max-w-[1200px] px-7">
        <div className="flex max-w-[880px] flex-col gap-4">
          <EyebrowDot>Retrieval</EyebrowDot>
          <h2 className="font-display text-[clamp(32px,4.2vw,52px)] font-bold leading-[1.05] tracking-[-0.03em] text-ink text-balance">
            Your team&apos;s memory,
            <br />
            <span className="font-medium text-dim">actually retrievable.</span>
          </h2>
          <p className="max-w-[620px] text-[17px] leading-[1.55] text-dim">
            Every retrieval method has blind spots, so Stash runs three:
            a curated wiki, vector search, and grep. Your agents get the
            best of all worlds.
          </p>
        </div>
        <div className="mt-12 grid grid-cols-1 gap-5 lg:grid-cols-3">
          <div>
            <PageGraphMock />
            <p className="mt-4 text-[13.5px] leading-[1.6] text-dim">
              While you sleep, an agent curates your history into linked
              pages — a virtual file system your agents navigate directly.
            </p>
          </div>
          <div>
            <EmbeddingProjection3D />
            <p className="mt-4 text-[13.5px] leading-[1.6] text-dim">
              Every session, page, and table embedded, so agents find
              knowledge by meaning — not filename.
            </p>
          </div>
          <div>
            <GrepSearchMock />
            <p className="mt-4 text-[13.5px] leading-[1.6] text-dim">
              Agents search your Stash like a repo — for the exact lookups
              embeddings miss.
            </p>
          </div>
        </div>
      </div>
    </section>
  );
}
