import type { Metadata } from "next";

import LegalShell from "../_components/LegalShell";

export const metadata: Metadata = {
  title: "Terms of Service · Stash",
  description:
    "The rules that govern your use of Stash, the managed service operated by Fergana Labs.",
};

function H2({ children }: { children: React.ReactNode }) {
  return (
    <h2 className="mt-10 font-display text-[22px] font-bold tracking-[-0.015em] text-ink">
      {children}
    </h2>
  );
}

export default function TermsPage() {
  return (
    <LegalShell title="Terms of Service" updated="April 21, 2026">
      <p>
        These Terms of Service (&ldquo;Terms&rdquo;) govern your use of the
        Stash managed service operated by Fergana Labs, Inc. (&ldquo;Fergana
        Labs,&rdquo; &ldquo;we,&rdquo; or &ldquo;us&rdquo;) at{" "}
        <a href="https://joinstash.ai" className="text-brand hover:underline">
          joinstash.ai
        </a>{" "}
        and its subdomains (the &ldquo;Service&rdquo;). By using the Service,
        you agree to these Terms. If you are using the Service on behalf of an
        organization, you represent that you have authority to bind that
        organization, and &ldquo;you&rdquo; refers to both you and that
        organization.
      </p>
      <p>
        The open-source Stash project is separately licensed under the MIT
        License and is not governed by these Terms.
      </p>

      <H2>Your account</H2>
      <p>
        You need an account to use the Service. You are responsible for keeping
        your credentials secure and for all activity under your account. Notify
        us promptly at{" "}
        <a
          href="mailto:hi@ferganalabs.com"
          className="text-brand hover:underline"
        >
          hi@ferganalabs.com
        </a>{" "}
        if you suspect unauthorized access. You must be at least 18 to use the
        Service.
      </p>

      <H2>Your content</H2>
      <p>
        You retain ownership of the content you and your agents submit to the
        Service (prompts, tool calls, notebooks, files, messages, and anything
        else you create in a workspace). You grant Fergana Labs a limited,
        worldwide, non-exclusive license to host, store, process, display, and
        transmit your content solely to operate and improve the Service for you
        and the members of your workspace.
      </p>
      <p>
        You are responsible for your content and for ensuring you have the
        rights to submit it. We do not monitor content, but we may remove
        content or suspend accounts that violate these Terms or applicable law.
      </p>

      <H2>Acceptable use</H2>
      <p>You agree not to:</p>
      <ul className="ml-5 list-disc space-y-2">
        <li>
          Use the Service to violate any law, infringe intellectual-property
          rights, or harm others.
        </li>
        <li>
          Upload or transmit malware, viruses, or other harmful code, or use
          the Service to attempt to gain unauthorized access to any system or
          data.
        </li>
        <li>
          Probe, scan, or load-test the Service without our prior written
          consent, or attempt to circumvent rate limits, quotas, or security
          controls.
        </li>
        <li>
          Resell, sublicense, or white-label the Service without a separate
          written agreement with us.
        </li>
        <li>
          Use the Service to generate or distribute content that is abusive,
          harassing, sexually explicit involving minors, or otherwise harmful.
        </li>
      </ul>

      <H2>Third-party services</H2>
      <p>
        The Service integrates with third-party AI models, authentication
        providers, and agent tools. Your use of those services is governed by
        their own terms, and we are not responsible for their availability or
        behavior.
      </p>

      <H2>Fees</H2>
      <p>
        Some features of the Service require a paid subscription. Fees, billing
        cycles, and usage limits are described at checkout. Paid fees are
        non-refundable except where required by law. We may change pricing with
        30 days&apos; notice for your next billing period.
      </p>

      <H2>Termination</H2>
      <p>
        You may cancel your account at any time from the app. We may suspend or
        terminate your access if you violate these Terms, if your account poses
        a security or legal risk, or if we discontinue the Service. On
        termination, your right to use the Service ends, and we will delete
        your content according to our Privacy Policy.
      </p>

      <H2>Warranty disclaimer</H2>
      <p>
        The Service is provided &ldquo;as is&rdquo; and &ldquo;as
        available.&rdquo; To the fullest extent permitted by law, Fergana Labs
        disclaims all warranties, express or implied, including merchantability,
        fitness for a particular purpose, and non-infringement. We do not
        warrant that the Service will be uninterrupted, error-free, or secure,
        or that agent-generated output will be accurate.
      </p>

      <H2>Limitation of liability</H2>
      <p>
        To the fullest extent permitted by law, Fergana Labs will not be liable
        for any indirect, incidental, special, consequential, or punitive
        damages, or for any loss of profits, revenue, data, or goodwill. Our
        total liability under these Terms is limited to the greater of (a) the
        amount you paid us in the 12 months before the claim, or (b) one
        hundred US dollars.
      </p>

      <H2>Indemnification</H2>
      <p>
        You agree to defend and indemnify Fergana Labs against any claim
        arising from your content, your use of the Service, or your violation
        of these Terms or applicable law.
      </p>

      <H2>Dispute resolution and binding arbitration</H2>
      <p>
        <strong className="text-ink">Please read this section carefully. It
        affects your legal rights, including your right to file a lawsuit in
        court.</strong>
      </p>
      <p>
        <strong className="text-ink">Federal Arbitration Act.</strong> These
        Terms affect interstate commerce and the enforceability of this
        section is governed by the Federal Arbitration Act, 9 U.S.C. § 1 et
        seq.
      </p>
      <p>
        <strong className="text-ink">Informal resolution first.</strong> Before
        starting an arbitration, you and Fergana Labs agree to try to resolve
        any dispute informally for at least 30 days. You can start this process
        by sending a written notice describing the dispute to{" "}
        <a
          href="mailto:hi@ferganalabs.com"
          className="text-brand hover:underline"
        >
          hi@ferganalabs.com
        </a>
        .
      </p>
      <p>
        <strong className="text-ink">Binding arbitration.</strong> Except for
        the carve-outs below, you and Fergana Labs agree that any dispute,
        claim, or controversy arising out of or relating to these Terms or the
        Service will be resolved by binding individual arbitration
        administered by the American Arbitration Association (AAA) under its
        Consumer Arbitration Rules then in effect. The arbitration will be
        conducted in English by a single arbitrator. You may choose to have the
        arbitration conducted by telephone, by video, based on written
        submissions, or in person in the county where you live or at another
        mutually agreed location. The arbitrator&apos;s decision is final and
        binding, and a judgment on the award may be entered in any court of
        competent jurisdiction.
      </p>
      <p>
        <strong className="text-ink">Arbitration fees.</strong> AAA&apos;s rules
        govern arbitration fees. For claims of $10,000 or less, Fergana Labs
        will pay all AAA filing, administrative, and arbitrator fees beyond any
        initial filing fee that you would have paid to file the same claim in
        court. For claims above $10,000, AAA&apos;s rules will determine how
        fees are allocated.
      </p>
      <p>
        <strong className="text-ink">Class-action and jury waiver.</strong> You
        and Fergana Labs agree that each of us may bring claims against the
        other only in our individual capacity, and not as a plaintiff or class
        member in any purported class, collective, representative, or
        consolidated action. The arbitrator may not consolidate claims or
        preside over any form of representative proceeding. Both parties waive
        the right to a jury trial.
      </p>
      <p>
        <strong className="text-ink">Carve-outs.</strong> Either party may (a)
        bring an individual claim in small-claims court so long as it qualifies
        and remains there, and (b) seek injunctive or other equitable relief
        in a court of competent jurisdiction to prevent actual or threatened
        infringement, misappropriation, or violation of intellectual-property
        or confidentiality rights.
      </p>
      <p>
        <strong className="text-ink">30-day opt-out.</strong> You can opt out of
        this arbitration agreement within 30 days of first accepting these
        Terms by emailing{" "}
        <a
          href="mailto:hi@ferganalabs.com"
          className="text-brand hover:underline"
        >
          hi@ferganalabs.com
        </a>{" "}
        with the subject line &ldquo;Arbitration Opt-Out&rdquo; and including
        your name and the email on your account. Opting out will not affect any
        other part of these Terms.
      </p>
      <p>
        If any part of this section is held unenforceable, the remainder
        remains in effect. If the class-action waiver is held unenforceable for
        a particular claim, that claim (and only that claim) will be resolved
        in court under the Governing law section below.
      </p>

      <H2>Governing law</H2>
      <p>
        These Terms are governed by the laws of the State of Delaware, USA,
        without regard to conflict-of-laws rules. Subject to the arbitration
        agreement above, any dispute that proceeds in court will be resolved
        exclusively in the state or federal courts located in Delaware, and you
        consent to personal jurisdiction there.
      </p>

      <H2>Changes</H2>
      <p>
        We may update these Terms from time to time. If we make material
        changes, we will notify you by email or in the app at least 30 days
        before they take effect. Your continued use of the Service after the
        effective date constitutes acceptance.
      </p>

      <H2>Contact</H2>
      <p>
        Questions about these Terms? Email us at{" "}
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
