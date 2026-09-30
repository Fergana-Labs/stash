import type { Metadata } from "next";
import Link from "next/link";

import SiteFooter from "../_components/SiteFooter";
import SiteHeader from "../_components/SiteHeader";
import ContactSalesForm from "./ContactSalesForm";

export const metadata: Metadata = {
  alternates: { canonical: "/contact-sales" },
  title: "Contact sales · Stash",
  description:
    "Book a demo of Stash for your team. Bring the agents you already run and we import real sessions on the call.",
};

const POINTS = [
  [
    "We start from your logs",
    "Bring a repository and the agents you already run. We import real sessions on the call.",
  ],
  [
    "Internal and external agents",
    "How one memory layer serves the agents your team runs and the agents your customers use.",
  ],
  ["Self-hosted or managed", "Deployment, security review, and pricing for either path."],
  ["Wiring help", "Claude Code, Cursor, Codex, OpenCode, Openclaw, and Hermes."],
];

export default function ContactSalesPage() {
  return (
    <main className="min-h-screen bg-background text-foreground">
      <SiteHeader />

      <section className="mx-auto grid max-w-[1180px] grid-cols-1 gap-10 px-5 pb-24 pt-16 sm:px-7 lg:grid-cols-[minmax(0,0.95fr)_minmax(0,1.05fr)] lg:gap-20">
        <div>
          <h1 className="max-w-[14ch] font-display text-[clamp(34px,4.4vw,54px)] font-medium leading-[1.06] tracking-[-0.028em] text-ink">
            Book a demo for <span className="text-brand">your team.</span>
          </h1>
          <p className="mt-[22px] max-w-[46ch] text-[17px] leading-[1.6] text-dim">
            Tell us about your setup and we will run a 30 minute walkthrough on your stack. No slide
            deck.
          </p>

          <dl className="mt-9 border-t border-border-subtle">
            {POINTS.map(([term, body]) => (
              <div key={term} className="border-b border-border-subtle py-4">
                <dt className="font-display text-[16.5px] font-medium tracking-[-0.02em] text-ink">
                  {term}
                </dt>
                <dd className="mt-1 text-[15px] leading-[1.6] text-dim">{body}</dd>
              </div>
            ))}
          </dl>

          <p className="mt-6 text-[15px] text-dim">
            In a hurry?{" "}
            <Link
              href={process.env.MANAGED_APP_URL || "https://app.joinstash.ai"}
              className="text-brand underline decoration-brand/40 underline-offset-4"
            >
              Sign up free
            </Link>{" "}
            and import your logs in one prompt, or email{" "}
            <a
              href="mailto:sam@joinstash.ai"
              className="text-brand underline decoration-brand/40 underline-offset-4"
            >
              sam@joinstash.ai
            </a>
            .
          </p>
        </div>

        <ContactSalesForm />
      </section>

      <SiteFooter />
    </main>
  );
}
