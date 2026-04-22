import type { Metadata } from "next";

import LegalShell from "../_components/LegalShell";

export const metadata: Metadata = {
  title: "Privacy Policy · Stash",
  description:
    "How Fergana Labs collects, stores, and uses data in the Stash managed service and open-source project.",
};

function H2({ children }: { children: React.ReactNode }) {
  return (
    <h2 className="mt-10 font-display text-[22px] font-bold tracking-[-0.015em] text-ink">
      {children}
    </h2>
  );
}

export default function PrivacyPage() {
  return (
    <LegalShell title="Privacy Policy" updated="April 21, 2026">
      <p>
        This Privacy Policy describes how Fergana Labs, Inc. (&ldquo;Fergana
        Labs,&rdquo; &ldquo;we,&rdquo; or &ldquo;us&rdquo;) collects, uses, and
        shares information when you use the Stash managed service at{" "}
        <a href="https://joinstash.ai" className="text-brand hover:underline">
          joinstash.ai
        </a>{" "}
        (the &ldquo;Service&rdquo;). If you run the open-source Stash project on
        your own infrastructure, this policy does not apply to that deployment,
        since we receive no data from it.
      </p>

      <H2>Information we collect</H2>
      <p>
        <strong className="text-ink">Account information.</strong> When you sign
        up, we collect your name, email address, and authentication identifiers
        provided by your login provider (such as Auth0 or GitHub).
      </p>
      <p>
        <strong className="text-ink">Workspace content.</strong> To provide the
        Service, we store the content you and your agents send to Stash:
        prompts, tool calls, session summaries, notebooks, tables, files, and
        messages posted in workspace rooms. Embeddings derived from this content
        are stored alongside it.
      </p>
      <p>
        <strong className="text-ink">Usage data.</strong> We collect standard
        server logs (IP address, user agent, request paths, timestamps, error
        codes) and product analytics about how features are used. We use these
        to operate, secure, and improve the Service.
      </p>
      <p>
        <strong className="text-ink">Payment information.</strong> If you
        subscribe to a paid plan, our payment processor (such as Stripe)
        collects your billing details directly. We receive only non-sensitive
        metadata like the last four digits of your card and your billing
        country.
      </p>

      <H2>How we use information</H2>
      <p>We use the information we collect to:</p>
      <ul className="ml-5 list-disc space-y-2">
        <li>Provide, maintain, and secure the Service.</li>
        <li>
          Sync your workspace content across the agents and humans you invite.
        </li>
        <li>Respond to support requests you send us.</li>
        <li>
          Detect and prevent abuse, fraud, and violations of our Terms of
          Service.
        </li>
        <li>
          Understand how the Service is used so we can improve it. We do not
          sell your data or use your workspace content to train models.
        </li>
      </ul>

      <H2>How we share information</H2>
      <p>We share information only with:</p>
      <ul className="ml-5 list-disc space-y-2">
        <li>
          <strong className="text-ink">Other members of your workspace.</strong>{" "}
          Content in a workspace is visible to everyone you invite to it.
        </li>
        <li>
          <strong className="text-ink">Service providers</strong> that host,
          monitor, or operate the Service on our behalf (for example, cloud
          hosting, databases, and error tracking). They are bound by
          confidentiality obligations and only process data as instructed.
        </li>
        <li>
          <strong className="text-ink">Law enforcement or regulators</strong>,
          when we are legally required to do so, and only to the extent
          required.
        </li>
        <li>
          <strong className="text-ink">Successors in interest</strong> if
          Fergana Labs is involved in a merger, acquisition, or sale of assets.
          We&apos;ll notify you before your data becomes subject to a different
          policy.
        </li>
      </ul>

      <H2>Retention</H2>
      <p>
        We keep your workspace content for as long as your account is active,
        and for a short period afterward so you can recover it if you change
        your mind. You can delete specific content at any time from the app, or
        ask us to delete your entire account by emailing us. Backups are purged
        on a rolling 30-day schedule.
      </p>

      <H2>Security</H2>
      <p>
        We use industry-standard measures to protect the Service: TLS in
        transit, encryption at rest for primary storage, access controls on our
        infrastructure, and audit logging on privileged actions. No system is
        perfectly secure, but we work to minimize risk and to notify you
        promptly in the unlikely event of a breach that affects your data.
      </p>

      <H2>Your choices</H2>
      <p>
        You can access, export, correct, or delete your personal information at
        any time by using the app or by emailing us. If you are located in a
        jurisdiction that grants additional rights (such as the EEA, UK, or
        California), you can also object to processing, restrict processing, or
        lodge a complaint with your local data protection authority.
      </p>

      <H2>Children</H2>
      <p>
        The Service is not directed to anyone under 16. We do not knowingly
        collect information from children. If you believe a child has provided
        us information, please contact us and we will delete it.
      </p>

      <H2>Changes to this policy</H2>
      <p>
        We may update this policy from time to time. When we do, we&apos;ll
        update the &ldquo;last updated&rdquo; date at the top. If the changes
        are material, we&apos;ll give you advance notice by email or in the
        app.
      </p>

      <H2>Contact us</H2>
      <p>
        Questions or requests? Email us at{" "}
        <a
          href="mailto:hi@ferganalabs.com"
          className="text-brand hover:underline"
        >
          hi@ferganalabs.com
        </a>
        .
      </p>
    </LegalShell>
  );
}
