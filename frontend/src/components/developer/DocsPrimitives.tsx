/** The Developer Platform's text primitives, ported from the docs page
 *  (`www/app/docs/components.tsx`) so the two read as one system.
 *
 *  Chillax caps at weight 600 per www/DESIGN.md — semibold, never bold, since
 *  anything heavier renders as faux-bold. */

export function PageHeading({
  title,
  children,
}: {
  title: string;
  children?: React.ReactNode;
}) {
  return (
    <header className="mb-10">
      <h1 className="font-display text-4xl font-semibold tracking-tight text-foreground">
        {title}
      </h1>
      {children && <p className="mt-3 max-w-2xl text-[17px] leading-8 text-dim">{children}</p>}
    </header>
  );
}

export function SectionHeading({ children }: { children: React.ReactNode }) {
  return <h2 className="font-display text-[20px] font-semibold text-foreground">{children}</h2>;
}

export function Code({ children }: { children: React.ReactNode }) {
  return (
    <code className="rounded-md bg-surface px-1.5 py-0.5 font-mono text-[13px] text-brand-700">
      {children}
    </code>
  );
}

export function CodeBlock({ children }: { children: string }) {
  return (
    <pre className="overflow-x-auto rounded-2xl border border-border bg-surface p-5 font-mono text-[12.5px] leading-6 text-dim">
      <code>{children}</code>
    </pre>
  );
}
