import type { Metadata } from "next";

import LegalShell from "../_components/LegalShell";

export const metadata: Metadata = {
  title: "Security · Stash",
  description: "How to report security vulnerabilities in Stash.",
};

function H2({ children }: { children: React.ReactNode }) {
  return (
    <h2 className="mt-10 font-display text-[22px] font-bold tracking-[-0.015em] text-ink">
      {children}
    </h2>
  );
}

export default function SecurityPage() {
  return (
    <LegalShell title="Security" updated="June 8, 2026">
      <p>
        Stash stores agent transcripts, workspace files, pages, copied
        integration data, and integration credentials. Please report any issue
        that could expose, modify, or delete customer data without authorization.
      </p>

      <H2>Report a vulnerability</H2>
      <p>
        Email{" "}
        <a href="mailto:sam@joinstash.ai" className="text-brand hover:underline">
          sam@joinstash.ai
        </a>{" "}
        with a concise description, affected URLs or endpoints, reproduction
        steps, and any evidence needed to understand impact. Do not include
        third-party customer data beyond the minimum needed to demonstrate the
        issue.
      </p>

      <H2>Response expectations</H2>
      <p>
        We acknowledge security reports within 2 business days, prioritize
        confirmed vulnerabilities by customer-data impact, and coordinate
        remediation details directly with the reporter.
      </p>

      <H2>Safe harbor</H2>
      <p>
        Good-faith testing must avoid service disruption, social engineering,
        spam, data destruction, persistence, and access to data that does not
        belong to you. If you encounter customer data, stop testing and report
        the issue with only the minimum evidence required.
      </p>
    </LegalShell>
  );
}
