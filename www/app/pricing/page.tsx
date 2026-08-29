import type { Metadata } from "next";
import Link from "next/link";

import SiteFooter from "../_components/SiteFooter";
import SiteHeader from "../_components/SiteHeader";

const APP_URL = process.env.MANAGED_APP_URL || "https://app.joinstash.ai";
const SIGNUP_URL = `${APP_URL}/login?mode=register`;

export const metadata: Metadata = {
  alternates: { canonical: "/pricing" },
  title: "Pricing · Stash",
  description:
    "Trace ingestion, search, and Skills are free. Pro supports Skill creation from up to 10,000 traces per month.",
};

// Every claim on this page mirrors what the backend actually enforces
// (billing_service + the curator credit gate). Change the enforcement and
// this page changes with it — never the other way around.
const TIERS: {
  name: string;
  price: string;
  priceDetail?: string;
  blurb: string;
  features: string[];
  cta: { label: string; href: string };
  featured?: boolean;
}[] = [
  {
    name: "Free",
    price: "$0",
    blurb: "Everything you need to give your coding agents memory.",
    features: [
      "Unlimited trace ingestion from supported coding agents",
      "Browse and search every trace",
      "Use all of your existing Skills",
      "Automatic curation of your first 1,000 useful traces",
      "Stash-managed inference — no model key required",
    ],
    cta: { label: "Sign up free", href: SIGNUP_URL },
  },
  {
    name: "Pro",
    price: "$20/month",
    priceDetail: "or $200/year — 2 months free",
    blurb: "Ten times the trace capacity for automatic Skill creation.",
    features: [
      "Everything in Free",
      "Skill creation from up to 10,000 traces each month",
      "Paused backlog resumes when your allowance resets",
      "Stash-managed inference — no model key required",
    ],
    cta: { label: "Start with Pro", href: SIGNUP_URL },
    featured: true,
  },
  {
    name: "Developer Platform",
    price: "Let's talk",
    blurb: "Memory for the agents inside your product, per end user.",
    features: [
      "A private wiki for each of your users",
      "One shared, anonymized wiki every user's agent reads",
      "Workspace keys, console, and curator controls",
      "Self-hosting support — MIT licensed, run it on your infra",
    ],
    cta: { label: "Book a call", href: "/contact-sales" },
  },
];

export default function PricingPage() {
  return (
    <main className="min-h-screen bg-background text-foreground">
      <SiteHeader current="Pricing" />

      <section className="px-5 pb-10 pt-14 text-center sm:px-7 md:pt-24">
        <h1 className="mx-auto max-w-[20ch] font-display text-[clamp(38px,5vw,60px)] font-medium leading-[1.06] tracking-[-0.028em] text-ink">
          Simple pricing.
        </h1>
        <p className="mx-auto mt-5 max-w-[52ch] text-[17px] leading-[1.6] text-dim">
          Trace ingestion, search, and Skills stay free. Pro supports ten times as many
          traces for automatic Skill creation.
        </p>
      </section>

      <section className="px-5 pb-16 sm:px-7 md:pb-24">
        <div className="mx-auto grid max-w-[1100px] grid-cols-1 gap-4 md:grid-cols-3">
          {TIERS.map((tier) => (
            <div
              key={tier.name}
              className={`flex flex-col rounded-[14px] border bg-white p-[26px] ${
                tier.featured ? "border-brand shadow-[0_12px_36px_-16px_rgba(0,0,0,0.18)]" : "border-border"
              }`}
            >
              <span className="font-mono text-[11.5px] uppercase tracking-[0.12em] text-muted">
                {tier.name}
              </span>
              <div className="mt-3.5 font-display text-[28px] font-medium tracking-[-0.028em] text-ink">
                {tier.price}
              </div>
              {tier.priceDetail && (
                <div className="mt-0.5 text-[13px] text-muted">{tier.priceDetail}</div>
              )}
              <p className="mt-3 text-[15px] leading-[1.6] text-dim">{tier.blurb}</p>
              <ul className="mt-5 space-y-2.5">
                {tier.features.map((f) => (
                  <li key={f} className="grid grid-cols-[14px_minmax(0,1fr)] gap-2.5 text-[14px] leading-[1.55] text-dim">
                    <span className="mt-[7px] block h-1.5 w-1.5 rounded-full bg-brand" />
                    {f}
                  </li>
                ))}
              </ul>
              <Link
                href={tier.cta.href}
                className={`mt-auto inline-flex h-[42px] items-center justify-center rounded-[10px] px-5 pt-0.5 text-[14.5px] font-medium transition ${
                  tier.featured
                    ? "bg-brand text-white hover:bg-brand-hover"
                    : "border border-border text-ink hover:border-ink"
                } mt-7`}
              >
                {tier.cta.label}
              </Link>
            </div>
          ))}
        </div>

        <p className="mx-auto mt-10 max-w-[60ch] text-center text-[14px] leading-[1.6] text-muted">
          At a hackathon? Your event code unlocks everything for free — redeem it during
          signup, or later under Settings → Subscription.
        </p>
      </section>

      <SiteFooter />
    </main>
  );
}
