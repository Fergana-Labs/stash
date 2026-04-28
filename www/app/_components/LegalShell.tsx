import Link from "next/link";
import type { ReactNode } from "react";

type Props = {
  title: string;
  updated: string;
  children: ReactNode;
};

export default function LegalShell({ title, updated, children }: Props) {
  return (
    <main className="min-h-screen bg-background text-foreground">
      <header className="sticky top-0 z-30 border-b border-border-subtle bg-background/85 backdrop-blur">
        <div className="mx-auto flex h-16 max-w-[1200px] items-center justify-between px-7">
          <Link
            href="/"
            className="font-display text-[20px] font-black tracking-[-0.03em] text-ink"
          >
            stash
          </Link>
          <nav className="flex items-center gap-6 text-[14px] text-dim">
            <Link href="/docs" className="transition hover:text-ink">
              Docs
            </Link>
            <Link href="/" className="transition hover:text-ink">
              Home
            </Link>
          </nav>
        </div>
      </header>

      <article className="mx-auto max-w-[760px] px-7 pb-24 pt-16">
        <p className="font-mono text-[11px] uppercase tracking-[0.14em] text-muted">
          Last updated {updated}
        </p>
        <h1 className="mt-3 font-display text-[clamp(36px,4.6vw,56px)] font-black leading-[1.05] tracking-[-0.03em] text-ink">
          {title}
        </h1>
        <div className="legal-prose mt-10 space-y-6 text-[16px] leading-[1.7] text-foreground">
          {children}
        </div>
        <p className="mt-16 border-t border-border-subtle pt-6 text-[14px] text-dim">
          Questions? Email{" "}
          <a
            href="mailto:sam@joinstash.ai"
            className="text-brand transition hover:underline"
          >
            sam@joinstash.ai
          </a>
          .
        </p>
      </article>
    </main>
  );
}
