import Link from "next/link";

// Building blocks used only by the reward model docs. The generic docs
// components live in ../components.tsx.

export function Table({ head, rows }: { head: string[]; rows: React.ReactNode[][] }) {
  return (
    <div className="my-6 overflow-x-auto rounded-2xl border border-border bg-surface">
      <table className="w-full text-sm">
        <thead>
          <tr className="bg-raised">
            {head.map((h) => (
              <th key={h} className="px-4 py-3 text-left text-xs font-medium uppercase tracking-wider text-muted">
                {h}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, i) => (
            <tr key={i} className="border-t border-border">
              {row.map((cell, j) => (
                <td
                  key={j}
                  className={`px-4 py-3 align-top text-xs leading-6 ${
                    j === 0 ? "whitespace-nowrap font-mono text-foreground" : "text-dim"
                  }`}
                >
                  {cell}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

const STAGES = [
  {
    n: "01",
    title: "Import",
    artifact: "traces.jsonl",
    body: "Eight formats in, one trace shape out.",
    href: "/reward-model-fine-tuning/trace-format",
  },
  {
    n: "02",
    title: "Annotate",
    artifact: "+1 / −1 · comment",
    body: "Highlight a span, rate it, say why.",
    href: "/reward-model-fine-tuning/annotations",
  },
  {
    n: "03",
    title: "Train",
    artifact: "r(trace) → score",
    body: "Bradley–Terry on + / − preference pairs.",
    href: "/reward-model-fine-tuning/training",
  },
  {
    n: "04",
    title: "Optimize",
    artifact: "best_prompt",
    body: "GEPA rewrites the system prompt.",
    href: "/reward-model-fine-tuning/gepa",
  },
];

// Ratings and comments take two different routes into the optimizer. The
// lanes below the stages show both.
export function Pipeline() {
  return (
    <figure className="my-8 overflow-hidden rounded-2xl border border-border bg-white">
      <div className="grid grid-cols-1 gap-px bg-border-subtle sm:grid-cols-2 lg:grid-cols-4">
        {STAGES.map((s) => (
          <Link key={s.n} href={s.href} className="group block bg-white px-5 py-5 transition-colors hover:bg-surface">
            <div className="font-mono text-[11px] text-muted">{s.n}</div>
            <div className="mt-1 font-display text-[19px] font-semibold text-ink group-hover:text-brand">
              {s.title}
            </div>
            <div className="mt-3 inline-block rounded-md border border-border-subtle bg-surface px-2 py-1 font-mono text-[12px] text-foreground">
              {s.artifact}
            </div>
            <p className="mt-3 text-[13px] leading-5 text-dim">{s.body}</p>
          </Link>
        ))}
      </div>
      <div className="border-t border-border-subtle bg-surface px-5 py-4 font-mono text-[12px] leading-7 text-dim">
        <Lane from="ratings" via={["preference pairs", "reward model"]} to="GEPA metric" />
        <Lane from="comments" via={["reflection feedback"]} to="GEPA proposer" />
      </div>
    </figure>
  );
}

function Lane({ from, via, to }: { from: string; via: string[]; to: string }) {
  return (
    <div className="flex flex-wrap items-center gap-x-2">
      <span className="w-[72px] text-foreground">{from}</span>
      {via.map((v) => (
        <span key={v} className="flex items-center gap-2">
          <span className="text-muted">→</span>
          <span>{v}</span>
        </span>
      ))}
      <span className="text-muted">→</span>
      <span className="text-foreground">{to}</span>
    </div>
  );
}

export function Endpoint({ method, path, children }: { method: string; path: string; children?: React.ReactNode }) {
  const color: Record<string, string> = {
    GET: "text-green-700",
    POST: "text-brand",
    PATCH: "text-amber-700",
    DELETE: "text-red-700",
  };
  return (
    <div className="mt-8 mb-3 flex flex-wrap items-baseline gap-3 border-b border-border-subtle pb-2">
      <code className={`font-mono text-[12px] font-semibold ${color[method]}`}>{method}</code>
      <code className="font-mono text-[14px] text-ink">/api/v1/rm{path}</code>
      {children && <span className="text-[13px] text-dim">{children}</span>}
    </div>
  );
}

export function NextPage({ href, label }: { href: string; label: string }) {
  return (
    <div className="mt-14 border-t border-border-subtle pt-6">
      <Link href={href} className="group inline-flex items-baseline gap-2 text-[15px] text-dim hover:text-ink">
        <span className="font-mono text-[11px] text-muted">Next</span>
        <span className="font-display font-semibold text-ink group-hover:text-brand">{label}</span>
        <span className="text-muted">→</span>
      </Link>
    </div>
  );
}
