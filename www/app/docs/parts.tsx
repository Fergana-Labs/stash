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

export { Pipeline } from "./pipeline";

// A looping, muted recording of a step in the Stash app, shown inline.
export function DemoClip({ src }: { src: string }) {
  return (
    <video
      src={src}
      autoPlay
      loop
      muted
      playsInline
      className="my-6 block aspect-[8/5] w-full rounded-2xl border border-border bg-surface"
    />
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
