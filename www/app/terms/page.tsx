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

      <H2>Electronic communications</H2>
      <p>
        By creating an account, you consent to receive communications from us
        electronically, including transactional emails, service and security
        notices, password resets, billing receipts, and changes to these Terms.
        These electronic communications satisfy any legal requirement that a
        communication be in writing. You are responsible for keeping the email
        address on your account current so that you receive our notices.
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

      <H2>Copyright complaints (DMCA)</H2>
      <p>
        We respond to notices of alleged copyright infringement under the
        Digital Millennium Copyright Act. If you believe content on the Service
        infringes a copyright you own, send a written notice to our designated
        agent at{" "}
        <a
          href="mailto:hi@ferganalabs.com"
          className="text-brand hover:underline"
        >
          hi@ferganalabs.com
        </a>{" "}
        that includes: (i) your physical or electronic signature; (ii)
        identification of the copyrighted work you claim is infringed; (iii)
        identification of the allegedly infringing material and its location on
        the Service; (iv) your contact information; (v) a statement that you
        have a good-faith belief the use is not authorized by the copyright
        owner, its agent, or the law; and (vi) a statement, under penalty of
        perjury, that the information is accurate and that you are authorized
        to act on behalf of the owner.
      </p>
      <p>
        We may terminate the accounts of users we determine to be repeat
        infringers.
      </p>

      <H2>Feedback</H2>
      <p>
        If you send us suggestions, ideas, or other feedback about the Service,
        you grant Fergana Labs a perpetual, irrevocable, worldwide, royalty-free
        license to use that feedback for any purpose without obligation or
        compensation to you.
      </p>

      <H2>Third-party services</H2>
      <p>
        The Service integrates with third-party AI models, authentication
        providers, and agent tools. Your use of those services is governed by
        their own terms, and we are not responsible for their availability or
        behavior.
      </p>

      <H2>Subscriptions, billing, and cancellation</H2>
      <p>
        <strong className="text-ink">Paid plans.</strong> Some features of the
        Service require a paid subscription. Current fees, billing cycles, and
        usage limits are shown at checkout and in your account settings. All
        fees are in US dollars and are exclusive of applicable taxes, which you
        are responsible for.
      </p>
      <p>
        <strong className="text-ink">Authorization to charge.</strong> By
        starting a paid subscription, you authorize Fergana Labs and its
        payment processor to charge the payment method on file for the
        applicable fees, taxes, and any other amounts incurred in connection
        with your use of the Service.
      </p>
      <p>
        <strong className="text-ink">Automatic renewal.</strong> Paid
        subscriptions automatically renew at the end of each billing period
        (monthly or annually, as selected at checkout) at the then-current
        price until you cancel. By subscribing, you agree to this automatic
        renewal. We will send a reminder before annual renewals where required
        by law.
      </p>
      <p>
        <strong className="text-ink">Free trials.</strong> If we offer a free
        trial, it will automatically convert to a paid subscription at the end
        of the trial period and your payment method will be charged at the
        then-current price unless you cancel before the trial ends.
      </p>
      <p>
        <strong className="text-ink">Cancellation.</strong> You can cancel a
        paid subscription at any time from your account settings. Cancellation
        takes effect at the end of the current billing period, and you will
        retain access through that date. We do not provide partial refunds for
        unused time.
      </p>
      <p>
        <strong className="text-ink">Refunds.</strong> Except as required by
        applicable law, all fees are non-refundable. If you believe you were
        charged in error, email{" "}
        <a
          href="mailto:hi@ferganalabs.com"
          className="text-brand hover:underline"
        >
          hi@ferganalabs.com
        </a>{" "}
        within 30 days of the charge and we will review your request in good
        faith.
      </p>
      <p>
        <strong className="text-ink">Price changes.</strong> We may change
        prices for the Service from time to time. We will give you at least 30
        days&apos; advance notice by email or in-app before the change applies
        to your next billing period. If you do not accept the new price, you
        can cancel before it takes effect.
      </p>
      <p>
        <strong className="text-ink">Failed payments.</strong> If a charge
        fails, we may retry the charge, downgrade your plan, or suspend access
        until the balance is resolved. You remain responsible for any unpaid
        amounts.
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
      <p className="uppercase">
        THE SERVICE IS PROVIDED &ldquo;AS IS&rdquo; AND &ldquo;AS
        AVAILABLE,&rdquo; WITHOUT WARRANTIES OF ANY KIND, EXPRESS OR IMPLIED.
        TO THE FULLEST EXTENT PERMITTED BY LAW, FERGANA LABS DISCLAIMS ALL
        WARRANTIES, INCLUDING IMPLIED WARRANTIES OF MERCHANTABILITY, FITNESS
        FOR A PARTICULAR PURPOSE, TITLE, AND NON-INFRINGEMENT, AND ANY
        WARRANTIES ARISING OUT OF COURSE OF DEALING OR USAGE OF TRADE.
      </p>
      <p className="uppercase">
        WE DO NOT WARRANT THAT THE SERVICE WILL BE UNINTERRUPTED, ERROR-FREE,
        OR SECURE, THAT DEFECTS WILL BE CORRECTED, OR THAT AGENT-GENERATED
        OUTPUT WILL BE ACCURATE, COMPLETE, OR SUITABLE FOR YOUR PURPOSES. YOU
        USE THE SERVICE AT YOUR OWN RISK.
      </p>

      <H2>Limitation of liability</H2>
      <p className="uppercase">
        TO THE FULLEST EXTENT PERMITTED BY LAW, IN NO EVENT WILL FERGANA LABS
        OR ITS OFFICERS, DIRECTORS, EMPLOYEES, OR AGENTS BE LIABLE FOR ANY
        INDIRECT, INCIDENTAL, SPECIAL, CONSEQUENTIAL, EXEMPLARY, OR PUNITIVE
        DAMAGES, OR FOR ANY LOSS OF PROFITS, REVENUE, DATA, GOODWILL, OR OTHER
        INTANGIBLE LOSSES, ARISING OUT OF OR RELATING TO THESE TERMS OR THE
        SERVICE, WHETHER BASED ON CONTRACT, TORT, STRICT LIABILITY, OR ANY
        OTHER LEGAL THEORY, AND WHETHER OR NOT FERGANA LABS HAS BEEN ADVISED
        OF THE POSSIBILITY OF SUCH DAMAGES.
      </p>
      <p className="uppercase">
        FERGANA LABS&rsquo; TOTAL AGGREGATE LIABILITY UNDER THESE TERMS WILL
        NOT EXCEED THE GREATER OF (A) THE AMOUNT YOU PAID US FOR THE SERVICE
        IN THE 12 MONTHS BEFORE THE EVENT GIVING RISE TO THE CLAIM, OR (B) ONE
        HUNDRED US DOLLARS ($100).
      </p>
      <p>
        Some jurisdictions do not allow the exclusion or limitation of certain
        damages, so some of the above may not apply to you. In those
        jurisdictions, our liability is limited to the smallest extent
        permitted by law.
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
