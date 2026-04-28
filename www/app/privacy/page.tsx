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
      <p>
        <strong className="text-ink">Cookies and device data.</strong> See the
        Cookies and tracking technologies section below.
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

      <H2>Cookies and tracking technologies</H2>
      <p>
        We use cookies and similar technologies (such as local storage and
        pixels) to operate, secure, and analyze the Service. The cookies we set
        fall into three categories:
      </p>
      <ul className="ml-5 list-disc space-y-2">
        <li>
          <strong className="text-ink">Strictly necessary cookies</strong>{" "}
          needed for you to sign in and use the Service. These cannot be turned
          off.
        </li>
        <li>
          <strong className="text-ink">Preference cookies</strong> that remember
          choices such as your workspace or display settings.
        </li>
        <li>
          <strong className="text-ink">Analytics cookies</strong> that help us
          understand how the Service is used so we can improve it. We do not
          use cookies for cross-site advertising.
        </li>
      </ul>
      <p>
        You can block or delete cookies through your browser settings. If you
        block strictly necessary cookies, parts of the Service may not work.
      </p>
      <p>
        <strong className="text-ink">Do Not Track and Global Privacy
        Control.</strong> Because there is no industry consensus on how to
        interpret Do Not Track signals, we do not respond to them. We do
        recognize the Global Privacy Control (GPC) signal as a valid
        opt-out-of-sale and opt-out-of-sharing request from California and
        other jurisdictions that treat GPC as such.
      </p>

      <H2>Your privacy rights</H2>
      <p>
        Depending on where you live, you may have the following rights in
        relation to your personal information:
      </p>
      <ul className="ml-5 list-disc space-y-2">
        <li>
          <strong className="text-ink">Access and portability.</strong> Request
          a copy of the personal information we hold about you.
        </li>
        <li>
          <strong className="text-ink">Correction.</strong> Ask us to correct
          inaccurate or incomplete information.
        </li>
        <li>
          <strong className="text-ink">Deletion.</strong> Ask us to delete your
          personal information.
        </li>
        <li>
          <strong className="text-ink">Objection or restriction.</strong>{" "}
          Object to or restrict certain processing.
        </li>
        <li>
          <strong className="text-ink">Withdraw consent</strong> where we rely
          on it as a legal basis.
        </li>
        <li>
          <strong className="text-ink">Appeal</strong> a denial of your rights
          request, where an appeal right applies.
        </li>
      </ul>
      <p>
        To exercise any of these rights, email{" "}
        <a
          href="mailto:sam@joinstash.ai"
          className="text-brand hover:underline"
        >
          sam@joinstash.ai
        </a>
        . We will respond within the timeframe required by applicable law. We
        will not discriminate against you for exercising your rights.
      </p>

      <H2>California privacy rights (CCPA/CPRA)</H2>
      <p>
        If you are a California resident, the California Consumer Privacy Act,
        as amended by the California Privacy Rights Act, gives you the rights
        described above and additional rights, including the right to know what
        personal information we collect, the right to opt out of the
        &ldquo;sale&rdquo; or &ldquo;sharing&rdquo; of your personal
        information, and the right to limit the use and disclosure of sensitive
        personal information.
      </p>
      <p>
        In the last 12 months, we have collected the categories of personal
        information described in the &ldquo;Information we collect&rdquo;
        section above, which map to the following CCPA categories: identifiers
        (name, email, account ID, IP address), commercial information (billing
        metadata), internet or network activity (usage logs), and electronic
        information you provide (workspace content). We collect this
        information from you directly and from your browser or device, and we
        share it only with the categories of recipients listed in the
        &ldquo;How we share information&rdquo; section.
      </p>
      <p>
        <strong className="text-ink">
          We do not sell your personal information, and we do not share it for
          cross-context behavioral advertising.
        </strong>{" "}
        We honor Global Privacy Control as an opt-out signal.
      </p>
      <p>
        You may designate an authorized agent to submit a rights request on
        your behalf. We will need to verify your identity and the agent&apos;s
        authority before acting.
      </p>

      <H2>EU, UK, and Swiss residents (GDPR)</H2>
      <p>
        If you are in the European Economic Area, the United Kingdom, or
        Switzerland, Fergana Labs is the controller of your personal
        information. We process your information on the following legal bases:
        to perform our contract with you (providing the Service); to comply
        with our legal obligations; for our legitimate interests in operating
        and securing the Service; and with your consent, where we ask for it.
      </p>
      <p>
        You have the rights listed in the &ldquo;Your privacy rights&rdquo;
        section above, as well as the right to lodge a complaint with your
        local data protection authority.
      </p>

      <H2>International data transfers</H2>
      <p>
        We are based in the United States, and our service providers may be
        located in other countries. When we transfer personal information out
        of the EEA, UK, or Switzerland, we rely on the European Commission&apos;s
        Standard Contractual Clauses, the UK International Data Transfer
        Addendum, or another lawful transfer mechanism.
      </p>

      <H2>Your choices</H2>
      <p>
        You can access, export, correct, or delete your personal information at
        any time by using the app or by emailing us. If you are located in a
        jurisdiction that grants additional rights (such as the EEA, UK, or
        California), the sections above explain how to exercise them.
      </p>

      <H2>Children</H2>
      <p>
        The Service is not directed to anyone under 18. We do not knowingly
        collect information from anyone under 18. If you believe a minor has
        provided us information, please contact us and we will delete it.
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
          href="mailto:sam@joinstash.ai"
          className="text-brand hover:underline"
        >
          sam@joinstash.ai
        </a>
        .
      </p>
    </LegalShell>
  );
}
