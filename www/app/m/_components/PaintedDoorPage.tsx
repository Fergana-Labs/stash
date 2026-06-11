import Link from "next/link";

import Logo from "../../_components/Logo";
import ScrollLink from "../../_components/ScrollLink";
import VariantSurvey from "./VariantSurvey";

const APP_URL = process.env.MANAGED_APP_URL || "https://app.joinstash.ai";

export type PaintedDoorCopy = {
  headline: string;
  subhead: string;
  bullets: { title: string; body: string }[];
};

// Minimal painted-door page for the message test: one message, three proof
// points written for that message, and the lead survey. No site nav — the
// only paths are the survey or leaving, so clicks measure the message.
export default function PaintedDoorPage({
  variant,
  copy,
}: {
  variant: string;
  copy: PaintedDoorCopy;
}) {
  const ctaClassName =
    "inline-flex h-11 items-center rounded-lg bg-brand px-6 text-[14.5px] font-medium text-white shadow-sm transition hover:bg-brand-hover";

  return (
    <main className="min-h-screen bg-background text-foreground">
      <header className="border-b border-border-subtle">
        <div className="mx-auto flex h-16 max-w-[1080px] items-center justify-between px-7">
          <Link
            href="/"
            className="flex items-center gap-2.5 font-display text-[20px] font-black tracking-[-0.03em] text-ink"
          >
            <Logo size={28} />
            stash
          </Link>
          <ScrollLink
            to="#survey"
            className="inline-flex h-10 items-center rounded-lg bg-brand px-[18px] text-[14px] font-medium text-white shadow-sm transition hover:bg-brand-hover"
          >
            Get early access
          </ScrollLink>
        </div>
      </header>

      <section className="relative overflow-hidden">
        <div
          aria-hidden
          className="pointer-events-none absolute inset-x-0 top-0 z-0 h-[480px]"
          style={{
            background:
              "radial-gradient(ellipse 80% 60% at 50% 0%, rgba(249,115,22,0.08), transparent 60%)",
          }}
        />
        <div className="relative z-10 mx-auto max-w-[860px] px-7 pb-20 pt-20 text-center md:pt-28">
          <p className="flex items-center justify-center font-mono text-[11px] font-medium uppercase tracking-[0.14em] text-muted">
            <span className="mr-[10px] inline-block h-[6px] w-[6px] rounded-full bg-brand" />
            Private beta
          </p>
          <h1 className="mt-5 text-balance font-display text-[clamp(40px,5.6vw,72px)] font-black leading-[1.02] tracking-[-0.04em] text-ink">
            {copy.headline}
          </h1>
          <p className="mx-auto mt-6 max-w-[600px] text-[18px] leading-[1.55] text-foreground">
            {copy.subhead}
          </p>
          <div className="mt-9 flex justify-center">
            <ScrollLink to="#survey" className={ctaClassName}>
              Get early access →
            </ScrollLink>
          </div>
        </div>
      </section>

      <section className="border-y border-border-subtle bg-surface py-16 md:py-20">
        <div className="mx-auto grid max-w-[1080px] grid-cols-1 gap-10 px-7 md:grid-cols-3 md:gap-12">
          {copy.bullets.map((b) => (
            <div key={b.title}>
              <h3 className="font-display text-[18px] font-bold tracking-[-0.015em] text-ink">
                {b.title}
              </h3>
              <p className="mt-2.5 text-[14.5px] leading-[1.6] text-dim">{b.body}</p>
            </div>
          ))}
        </div>
      </section>

      <VariantSurvey variant={variant} appUrl={APP_URL} />

      <footer className="border-t border-border-subtle">
        <div className="mx-auto flex max-w-[1080px] flex-wrap items-center justify-between gap-3 px-7 py-5 font-mono text-[11px] uppercase tracking-[0.12em] text-muted">
          <span>© 2026 Fergana Labs</span>
          <span className="flex gap-5">
            <Link href="/privacy" className="transition hover:text-ink">
              Privacy
            </Link>
            <Link href="/terms" className="transition hover:text-ink">
              Terms
            </Link>
          </span>
        </div>
      </footer>
    </main>
  );
}
