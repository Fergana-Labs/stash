import Link from "next/link";

import {
  ClosingCTA,
  Comparisons,
  Features,
  Footer,
  HeroFunnel,
  HowItWorks,
  Logos,
  type HowItWorksStep,
} from "../../_components/HomePage";
import ScrollLink from "../../_components/ScrollLink";
import SiteHeader from "../../_components/SiteHeader";
import VariantSurvey from "./VariantSurvey";

const APP_URL = process.env.MANAGED_APP_URL || "https://app.joinstash.ai";

export type VariantCopy = {
  headline: string;
  subhead: string;
  // The drive message is about the Drive itself, so it keeps the hero image.
  showHeroFunnel?: boolean;
  how: { title: string; subtitle: string; steps: HowItWorksStep[] };
};

// A complete landing page per message under test: real header and sections,
// hero + "How it works" rewritten for the message, and every signup CTA
// anchored to the sign-up survey after the closing CTA.
export default function VariantLanding({
  variant,
  copy,
}: {
  variant: string;
  copy: VariantCopy;
}) {
  return (
    <main className="min-h-screen bg-background text-foreground">
      <SiteHeader ctaHref="#survey" />
      <VariantHero copy={copy} />
      <Logos />
      <HowItWorks
        title={copy.how.title}
        subtitle={copy.how.subtitle}
        steps={copy.how.steps}
      />
      <Comparisons />
      <Features />
      <ClosingCTA ctaHref="#survey" />
      <VariantSurvey variant={variant} appUrl={APP_URL} />
      <Footer />
    </main>
  );
}

function VariantHero({ copy }: { copy: VariantCopy }) {
  const text = (
    <div className={copy.showHeroFunnel ? "" : "mx-auto max-w-[820px] text-center"}>
      <h1 className="text-balance font-display text-[clamp(40px,5.6vw,72px)] font-black leading-[1.02] tracking-[-0.04em] text-ink">
        {copy.headline}
      </h1>
      <p
        className={
          "mt-7 max-w-[560px] text-[18px] leading-[1.55] text-foreground" +
          (copy.showHeroFunnel ? "" : " mx-auto")
        }
      >
        {copy.subhead}
      </p>
      <div
        className={
          "mt-9 flex flex-wrap items-center gap-3" +
          (copy.showHeroFunnel ? "" : " justify-center")
        }
      >
        <ScrollLink
          to="#survey"
          className="inline-flex h-11 items-center rounded-lg bg-brand px-5 text-[14px] font-medium text-white shadow-sm transition hover:bg-brand-hover"
        >
          Start free →
        </ScrollLink>
        <Link
          href="/contact-sales"
          className="inline-flex h-11 items-center rounded-lg border border-border bg-background px-5 text-[14px] font-medium text-ink transition hover:border-ink"
        >
          Talk to us
        </Link>
      </div>
    </div>
  );

  return (
    <section className="relative overflow-hidden">
      <div
        aria-hidden
        className="pointer-events-none absolute inset-x-0 top-0 z-0 h-[680px]"
        style={{
          background: copy.showHeroFunnel
            ? "radial-gradient(ellipse 80% 60% at 20% 10%, rgba(249,115,22,0.09), transparent 60%)"
            : "radial-gradient(ellipse 80% 60% at 50% 0%, rgba(249,115,22,0.08), transparent 60%)",
        }}
      />
      <div className="relative z-10 mx-auto max-w-[1200px] px-7 pb-12 pt-20 lg:pb-20 lg:pt-28">
        {copy.showHeroFunnel ? (
          <div className="grid grid-cols-1 gap-12 lg:grid-cols-[minmax(0,1.05fr)_minmax(0,0.95fr)] lg:items-center lg:gap-16">
            {text}
            <HeroFunnel />
          </div>
        ) : (
          text
        )}
      </div>
    </section>
  );
}
