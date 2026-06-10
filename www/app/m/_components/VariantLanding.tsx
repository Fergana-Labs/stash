import Link from "next/link";

import {
  ClosingCTA,
  Comparisons,
  Features,
  Footer,
  HeroFunnel,
  HowItWorks,
  Logos,
} from "../../_components/HomePage";
import SiteHeader from "../../_components/SiteHeader";
import type { VariantCopy } from "../variants";
import CaptureLanding from "./CaptureLanding";

// A complete landing page per message under test: real header and sections,
// hero + "How it works" rewritten for the message. Every signup CTA leads to
// the variant's /signup flow instead of the app.
export default function VariantLanding({
  variant,
  copy,
}: {
  variant: string;
  copy: VariantCopy;
}) {
  const signupHref = `/m/${variant}/signup`;
  return (
    <main className="min-h-screen bg-background text-foreground">
      <CaptureLanding variant={variant} />
      <SiteHeader ctaHref={signupHref} />
      <VariantHero copy={copy} signupHref={signupHref} />
      <Logos />
      <HowItWorks
        title={copy.how.title}
        subtitle={copy.how.subtitle}
        steps={copy.how.steps}
      />
      <Comparisons />
      <Features />
      <ClosingCTA ctaHref={signupHref} />
      <Footer />
    </main>
  );
}

function VariantHero({
  copy,
  signupHref,
}: {
  copy: VariantCopy;
  signupHref: string;
}) {
  return (
    <section className="relative overflow-hidden">
      <div
        aria-hidden
        className="pointer-events-none absolute inset-x-0 top-0 z-0 h-[680px]"
        style={{
          background:
            "radial-gradient(ellipse 80% 60% at 20% 10%, rgba(249,115,22,0.09), transparent 60%)",
        }}
      />
      <div className="relative z-10 mx-auto max-w-[1200px] px-7 pb-12 pt-20 lg:pb-20 lg:pt-28">
        <div className="grid grid-cols-1 gap-12 lg:grid-cols-[minmax(0,1.05fr)_minmax(0,0.95fr)] lg:items-center lg:gap-16">
          <div>
            <h1 className="text-balance font-display text-[clamp(40px,5.6vw,72px)] font-black leading-[1.02] tracking-[-0.04em] text-ink">
              {copy.headline}
            </h1>
            <p className="mt-7 max-w-[560px] text-[18px] leading-[1.55] text-foreground">
              {copy.subhead}
            </p>
            <div className="mt-9 flex flex-wrap items-center gap-3">
              <Link
                href={signupHref}
                className="inline-flex h-11 items-center rounded-lg bg-brand px-5 text-[14px] font-medium text-white shadow-sm transition hover:bg-brand-hover"
              >
                Start free →
              </Link>
              <Link
                href="/contact-sales"
                className="inline-flex h-11 items-center rounded-lg border border-border bg-background px-5 text-[14px] font-medium text-ink transition hover:border-ink"
              >
                Talk to us
              </Link>
            </div>
          </div>
          <HeroFunnel />
        </div>
      </div>
    </section>
  );
}
