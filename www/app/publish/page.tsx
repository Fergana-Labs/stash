import Link from "next/link";
import type { Metadata } from "next";

import CopyButton from "../_components/CopyButton";

const APP_URL = process.env.NEXT_PUBLIC_APP_URL || "https://app.joinstash.ai";
const TWEET_URL = "https://x.com/trq212/status/2052809885763747935";

const SAMPLE_PROMPT = `Make an HTML page about how our rate limiter works. Be information-dense, use SVG diagrams, code snippets, optimize for one-time read.

When you're done, publish to Stash and print the share URL:

curl -sS -X POST ${APP_URL}/api/v1/publish \\
  -H "Authorization: Bearer $STASH_KEY" \\
  -H "Content-Type: application/json" \\
  -d @- <<'EOF'
{ "title": "...", "content_type": "html", "content": "...", "audience": "link" }
EOF`;

export const metadata: Metadata = {
  title: "Your agent makes HTML. We make it shareable. · Stash",
  description:
    "Stash takes the HTML your coding agent produces and turns it into a share URL. One prompt, one curl, one link your teammates can open.",
  openGraph: {
    title: "Your agent makes HTML. We make it shareable.",
    description:
      "One prompt to your coding agent — get a share URL back. Built for the unreasonable effectiveness of HTML.",
    type: "website",
    url: "/publish",
    siteName: "Stash",
  },
};

export default function PublishLandingPage() {
  return (
    <main className="min-h-screen bg-background text-foreground">
      <Nav />
      <Hero />
      <Pitch />
      <Demo />
      <UseCases />
      <ClosingCTA />
    </main>
  );
}

function Logo({ size = 28 }: { size?: number }) {
  return (
    <svg
      xmlns="http://www.w3.org/2000/svg"
      viewBox="0 0 64 72"
      width={size}
      height={(size * 72) / 64}
      aria-hidden="true"
    >
      <ellipse cx="32" cy="24" rx="22" ry="18" fill="#F97316" />
      <circle cx="25" cy="22" r="4" fill="#fff" />
      <circle cx="39" cy="22" r="4" fill="#fff" />
      <circle cx="26" cy="22" r="2" fill="#0F172A" />
      <circle cx="40" cy="22" r="2" fill="#0F172A" />
      <path d="M12 38 Q8 52 4 60" stroke="#F97316" strokeWidth="4" strokeLinecap="round" fill="none" />
      <path d="M20 40 Q18 54 14 62" stroke="#F97316" strokeWidth="4" strokeLinecap="round" fill="none" />
      <path d="M32 42 Q32 56 32 64" stroke="#F97316" strokeWidth="4" strokeLinecap="round" fill="none" />
      <path d="M44 40 Q46 54 50 62" stroke="#F97316" strokeWidth="4" strokeLinecap="round" fill="none" />
      <path d="M52 38 Q56 52 60 60" stroke="#F97316" strokeWidth="4" strokeLinecap="round" fill="none" />
    </svg>
  );
}

function Nav() {
  return (
    <header className="sticky top-0 z-50 border-b border-border-subtle bg-background/80 backdrop-blur">
      <div className="mx-auto flex h-16 max-w-[1200px] items-center justify-between px-7">
        <Link
          href="/"
          className="flex items-center gap-2.5 font-display text-[20px] font-black tracking-[-0.03em] text-ink"
        >
          <Logo size={28} />
          stash
        </Link>
        <nav className="flex items-center gap-2 text-[14px] text-dim">
          <Link
            href="/docs"
            className="hidden rounded-md px-3 py-2 transition hover:bg-raised hover:text-ink sm:inline-flex"
          >
            Docs
          </Link>
          <Link
            href={`${APP_URL}/login`}
            className="hidden rounded-md px-3 py-2 transition hover:bg-raised hover:text-ink sm:inline-flex"
          >
            Sign in
          </Link>
          <Link
            href={`${APP_URL}/login?mode=register&from=publish`}
            className="inline-flex h-10 items-center rounded-lg bg-brand px-[18px] text-[14px] font-medium text-white transition hover:bg-brand-hover"
          >
            Get started free
          </Link>
        </nav>
      </div>
    </header>
  );
}

function Hero() {
  return (
    <section className="relative overflow-hidden">
      <div
        aria-hidden
        className="pointer-events-none absolute inset-x-0 top-0 z-0 h-[680px]"
        style={{
          background:
            "radial-gradient(ellipse 80% 60% at 30% 10%, rgba(249,115,22,0.12), transparent 60%)",
        }}
      />
      <div className="relative z-10 mx-auto max-w-[1100px] px-7 pb-12 pt-20 lg:pt-28">
        <a
          href={TWEET_URL}
          target="_blank"
          rel="noreferrer"
          className="inline-flex items-center gap-2.5 rounded-full border border-border bg-white/70 py-[5px] pl-[5px] pr-3.5 text-[12px] text-dim shadow-sm transition hover:border-brand/40 hover:text-ink"
        >
          <span className="rounded-full bg-brand px-2 py-0.5 font-mono text-[10px] font-bold uppercase tracking-[0.12em] text-white">
            Why
          </span>
          <span>
            Inspired by Thariq Shihipar (Anthropic):{" "}
            <em>The Unreasonable Effectiveness of HTML</em>
          </span>
          <span className="font-mono text-muted">→</span>
        </a>

        <h1 className="mt-7 max-w-[920px] text-balance font-display text-[clamp(44px,6.4vw,80px)] font-black leading-[0.95] tracking-[-0.045em] text-ink">
          Your agent makes <span className="text-brand">HTML.</span>
          <br />
          We make it <span className="text-brand">shareable.</span>
        </h1>

        <p className="mt-7 max-w-[640px] text-[18px] leading-[1.55] text-foreground">
          Markdown specs go unread. HTML pages get opened, scrolled, and
          forwarded. The catch: most teams have nowhere to put them. One prompt
          to your coding agent, one curl, one link your teammates can open. No
          MCP setup, no S3 bucket.
        </p>

        <div className="mt-9 flex flex-wrap items-center gap-3">
          <Link
            href={`${APP_URL}/login?mode=register&from=publish`}
            className="inline-flex h-12 items-center rounded-lg bg-brand px-6 text-[15px] font-semibold text-white transition hover:bg-brand-hover"
          >
            Get a share URL in 60 seconds
          </Link>
          <a
            href="#how"
            className="inline-flex h-12 items-center rounded-lg border border-border px-5 text-[15px] font-medium text-ink transition hover:border-ink"
          >
            See how it works
          </a>
        </div>

        <p className="mt-5 max-w-[640px] font-mono text-[12px] uppercase tracking-[0.12em] text-muted">
          Free · works with Claude Code, Cursor, Codex, OpenCode
        </p>
      </div>
    </section>
  );
}

function Pitch() {
  return (
    <section className="border-t border-border-subtle bg-surface">
      <div className="mx-auto max-w-[1100px] px-7 py-20">
        <p className="font-mono text-[11px] uppercase tracking-[0.14em] text-muted">
          Why HTML, why now
        </p>
        <h2 className="mt-3 max-w-[760px] font-display text-[clamp(28px,3.2vw,42px)] font-bold leading-[1.1] tracking-[-0.02em] text-ink">
          Markdown was for humans typing alone. HTML is for agents working with
          you.
        </h2>
        <p className="mt-5 max-w-[680px] text-[15px] leading-[1.6] text-foreground">
          As{" "}
          <a
            href={TWEET_URL}
            target="_blank"
            rel="noreferrer"
            className="text-brand underline decoration-brand/30 underline-offset-4 hover:decoration-brand"
          >
            Thariq Shihipar at Anthropic put it
          </a>
          : the chance of someone actually reading your spec, report, or PR
          writeup is much higher in HTML. The friction was always{" "}
          <em>where to put it</em>. Stash is the answer.
        </p>

        <div className="mt-12 grid grid-cols-1 gap-6 md:grid-cols-3">
          <PitchCard
            tag="Information density"
            title="One file, every shape of information."
            body="Tables, SVG diagrams, color, code, sliders, canvases. Everything markdown forced into a fenced block, HTML renders in line. Your agent gets a richer canvas; you get a richer artifact."
          />
          <PitchCard
            tag="Ease of sharing"
            title="No S3, no attachment, no rendering quirks."
            body="The curl call publishes the page and prints a URL. Your teammates open it in a browser and read it. The page lives in your workspace, indexed and searchable, not lost in chat."
          />
          <PitchCard
            tag="Stay in the loop"
            title="You stop skimming. You start reading."
            body="A 100-line markdown plan is a wall. The same content as HTML — with sections, diagrams, navigation — is something you actually read end-to-end. You stay in the loop with what your agent is doing."
          />
        </div>
      </div>
    </section>
  );
}

function PitchCard({
  tag,
  title,
  body,
}: {
  tag: string;
  title: string;
  body: string;
}) {
  return (
    <article className="rounded-2xl border border-border-subtle bg-background p-6">
      <p className="font-mono text-[11px] uppercase tracking-[0.14em] text-brand">
        {tag}
      </p>
      <h3 className="mt-3 font-display text-[20px] font-bold leading-[1.2] tracking-[-0.01em] text-ink">
        {title}
      </h3>
      <p className="mt-3 text-[14px] leading-[1.6] text-foreground">{body}</p>
    </article>
  );
}

function Demo() {
  return (
    <section id="how" className="border-t border-border-subtle">
      <div className="mx-auto max-w-[1100px] px-7 py-20">
        <p className="font-mono text-[11px] uppercase tracking-[0.14em] text-muted">
          The 60 seconds
        </p>
        <h2 className="mt-3 font-display text-[clamp(28px,3.2vw,42px)] font-bold leading-[1.1] tracking-[-0.02em] text-ink">
          Sign up. Paste one block. Done.
        </h2>

        <ol className="mt-10 space-y-6">
          <Step
            n={1}
            title="Sign up"
            body="Create an account on Stash. We auto-provision a workspace for you and hand you a personal API key."
          />
          <Step
            n={2}
            title="Paste this prompt into your coding agent"
            body="Drop the block into Claude Code, Cursor, Codex, or OpenCode. The agent writes the HTML and runs the curl that publishes it."
          >
            <div
              className="mt-4 overflow-hidden rounded-[14px] border border-white/5 bg-inverted"
              style={{ boxShadow: "var(--shadow-terminal)" }}
            >
              <div className="flex items-center justify-between border-b border-white/5 px-3.5 py-2.5">
                <div className="flex items-center gap-3">
                  <div className="flex gap-1.5">
                    <span className="h-2.5 w-2.5 rounded-full bg-white/10" />
                    <span className="h-2.5 w-2.5 rounded-full bg-white/10" />
                    <span className="h-2.5 w-2.5 rounded-full bg-white/10" />
                  </div>
                  <span className="font-mono text-[11px] font-medium uppercase tracking-[0.14em] text-on-inverted-dim">
                    prompt.txt
                  </span>
                </div>
                <CopyButton
                  value={SAMPLE_PROMPT}
                  label="copy"
                  copiedLabel="copied ✓"
                  className="inline-flex h-[26px] items-center rounded-md border border-white/10 bg-transparent px-2.5 font-mono text-[10.5px] uppercase tracking-[0.1em] text-on-inverted-dim transition hover:border-white/30 hover:text-white data-[copied=true]:border-[rgba(34,197,94,0.5)] data-[copied=true]:text-[#22C55E]"
                />
              </div>
              <pre className="overflow-x-auto px-5 py-5 font-mono text-[12.5px] leading-[1.7] text-on-inverted whitespace-pre-wrap break-words">
                {SAMPLE_PROMPT}
              </pre>
            </div>
          </Step>
          <Step
            n={3}
            title="Open the URL the agent prints"
            body="The curl prints a link like app.joinstash.ai/v/abc123. Your page is live, public-with-the-link, and lives in your workspace where you can rename it, share it, or pull it into a Stash with teammates later."
          />
        </ol>
      </div>
    </section>
  );
}

function Step({
  n,
  title,
  body,
  children,
}: {
  n: number;
  title: string;
  body: string;
  children?: React.ReactNode;
}) {
  return (
    <li className="flex gap-5">
      <span className="shrink-0 inline-flex h-9 w-9 items-center justify-center rounded-full bg-brand/10 font-mono text-[13px] font-semibold text-brand">
        {n}
      </span>
      <div className="flex-1 min-w-0">
        <h3 className="font-display text-[18px] font-bold tracking-[-0.01em] text-ink">
          {title}
        </h3>
        <p className="mt-1.5 max-w-[680px] text-[14.5px] leading-[1.6] text-foreground">
          {body}
        </p>
        {children}
      </div>
    </li>
  );
}

function UseCases() {
  const cases: { title: string; body: string }[] = [
    {
      title: "Specs, planning, exploration",
      body: "Six side-by-side onboarding mockups in one HTML grid. An implementation plan with diagrams and code. The artifact you actually pass to the next session.",
    },
    {
      title: "Code review & PR explainers",
      body: "Render the diff, color-code findings by severity, annotate the streaming logic. Better than the default GitHub diff for the parts your reviewer needs.",
    },
    {
      title: "Design & prototypes",
      body: "Sketch a checkout button with sliders for animation params. Tune in the values. Copy the parameters back into the prompt to ship the real component.",
    },
    {
      title: "Reports & research",
      body: "Synthesize across your codebase, Slack, and git history into a single readable explainer with SVG flowcharts. The thing you wish you had before the incident review.",
    },
    {
      title: "Custom editing interfaces",
      body: "A throwaway drag-and-drop board for reprioritizing 30 Linear tickets. A form-based editor for feature flags with dependency warnings. Export the result back as JSON.",
    },
    {
      title: "Joyful artifacts",
      body: "It just feels better. You make the thing, you read the thing, you send the thing. Your team reads it back. The work compounds instead of evaporating.",
    },
  ];
  return (
    <section className="border-t border-border-subtle bg-surface">
      <div className="mx-auto max-w-[1100px] px-7 py-20">
        <p className="font-mono text-[11px] uppercase tracking-[0.14em] text-muted">
          Use cases
        </p>
        <h2 className="mt-3 max-w-[760px] font-display text-[clamp(28px,3.2vw,42px)] font-bold leading-[1.1] tracking-[-0.02em] text-ink">
          What people are publishing.
        </h2>
        <p className="mt-4 max-w-[640px] text-[15px] leading-[1.6] text-foreground">
          The categories are Thariq&rsquo;s. The point is the same: anything you
          can ask for, your agent can render as HTML. We make it shareable.
        </p>
        <div className="mt-10 grid grid-cols-1 gap-5 md:grid-cols-2 lg:grid-cols-3">
          {cases.map((c) => (
            <article
              key={c.title}
              className="rounded-xl border border-border-subtle bg-background p-5"
            >
              <h3 className="font-display text-[16px] font-bold tracking-[-0.01em] text-ink">
                {c.title}
              </h3>
              <p className="mt-2 text-[13.5px] leading-[1.55] text-foreground">
                {c.body}
              </p>
            </article>
          ))}
        </div>
      </div>
    </section>
  );
}

function ClosingCTA() {
  return (
    <section className="border-t border-border-subtle">
      <div className="mx-auto max-w-[1100px] px-7 py-20 text-center">
        <h2 className="mx-auto max-w-[720px] font-display text-[clamp(30px,3.6vw,46px)] font-bold leading-[1.1] tracking-[-0.02em] text-ink">
          Make the thing. Share the link. Compound the work.
        </h2>
        <p className="mx-auto mt-5 max-w-[560px] text-[16px] leading-[1.6] text-foreground">
          Sign up free. Sixty seconds to your first share URL. No credit card,
          no install.
        </p>
        <div className="mt-8 flex flex-wrap items-center justify-center gap-3">
          <Link
            href={`${APP_URL}/login?mode=register&from=publish`}
            className="inline-flex h-12 items-center rounded-lg bg-brand px-6 text-[15px] font-semibold text-white transition hover:bg-brand-hover"
          >
            Get started free
          </Link>
          <a
            href={TWEET_URL}
            target="_blank"
            rel="noreferrer"
            className="inline-flex h-12 items-center rounded-lg border border-border px-5 text-[15px] font-medium text-ink transition hover:border-ink"
          >
            Read Thariq&rsquo;s post
          </a>
        </div>
      </div>
    </section>
  );
}
