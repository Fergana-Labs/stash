import type { Metadata } from "next";
import Link from "next/link";

export const metadata: Metadata = {
  title:
    "Giving yourself superpowers: Advice on building a simple company brain · Stash",
  description:
    "An opinionated take on the right way to build a company brain so your AI agents can do real knowledge work: integrations, retrieval, memory, and privacy.",
};

export default function HowToBuildACompanyBrainPage() {
  return (
    <main className="min-h-screen bg-background text-foreground">
      <Header />

      <article className="mx-auto max-w-[720px] px-7 pb-24 pt-16">
        <p className="flex items-center font-mono text-[11px] font-medium uppercase tracking-[0.14em] text-muted">
          <span className="mr-[10px] inline-block h-[6px] w-[6px] rounded-full bg-brand" />
          Blog
        </p>
        <h1 className="mt-5 text-balance font-display text-[clamp(32px,4.4vw,52px)] font-black leading-[1.04] tracking-[-0.035em] text-ink">
          Giving yourself superpowers: Advice on building a simple company brain
        </h1>
        <p className="mt-5 text-[14px] text-muted">By Henry Dowling · June 2026</p>

        <div className="prose prose-lg mt-10">
          <p>
            If you do skilled knowledge work at a company (for example,
            you&rsquo;re the CPO of a startup, or you&rsquo;re leading AI
            transformation at a consulting company), it&rsquo;s a really good
            idea to build a <strong>company brain</strong>.
          </p>
          <p>
            In this article, I&rsquo;ll give my opinionated take on the correct
            way to build a company brain so that you can leverage yours as
            effectively as possible.
          </p>

          <h2>What problem does a company brain solve anyway?</h2>
          <p>
            Company brains exist because recently, smart knowledge workers (e.g.
            consultants, investment bankers, product managers) have started using
            AI agents (e.g. Claude Code) to do <em>general knowledge work</em>{" "}
            besides coding. This means making excel sheets and powerpoints,
            writing audit
            reports, etc.
          </p>
          <p>
            There&rsquo;s a problem that you run into whenever you try to use AI
            agents for knowledge work: they need a lot of context on stuff going
            on in your organization. For example, they need access to your email,
            Slack/Microsoft Teams, Jira, SharePoint, etc.
          </p>
          <p>
            <strong>
              <em>A company brain solves this problem</em>
            </strong>
            : it helps your agents find the information they need in order to do
            knowledge work tasks. E.g. if you
            need revenue numbers from a sheet in Google Sheets and details about a
            customer from Gong in order to make a sales deck, a company brain
            allows your agent to seamlessly find this info.
          </p>
          <p>
            Modern company brains also include additional affordances including
            memory (i.e. summarization of learnings from agent trajectories in the
            company) and tracking of agent usage (i.e. sharing agent transcripts).
          </p>

          <h2>How are you supposed to use a company brain?</h2>
          <p>
            The way that I like to think about it is that if you are doing a
            company brain &ldquo;right&rdquo;, you are giving yourself a bunch of{" "}
            <strong>superpowers</strong> as an IC. This is especially important now
            given the trend
            that &ldquo;everyone is an IC&rdquo;, even (especially) execs.
          </p>
          <p>
            As you use your company brain more, you&rsquo;ll learn what use cases
            are most useful to you, but in order to get started and get an idea of
            what some &ldquo;superpowers&rdquo; can look like, I&rsquo;ll list some
            examples below.
          </p>
          <ul>
            <li>
              <strong>
                Support your roadmap decisions with exact numbers from sales
                calls.
              </strong>{" "}
              Check in on Gong sales calls to see how many mentions of upcoming
              candidate projects for your roadmap there are.
            </li>
            <li>
              <strong>
                Be insanely well-prepared for meeting with your direct reports.
              </strong>{" "}
              Prepare for a 1:1 with a direct report by asking for a rundown of
              every public artifact that your direct report has created&mdash;this
              includes Slack messages, meeting transcripts that you have access
              to, etc.
            </li>
            <li>
              <strong>Be the best user of AI in your organization.</strong> Audit
              all of your past conversations with your AI agent to learn what you
              could be doing better (this is the general idea of recursive
              self-improvement in the context of a company&mdash;use AI to help you
              improve your organization more efficiently with AI).
            </li>
          </ul>
          <a
            href="https://x.com/dflieb/status/2066202214625165577"
            target="_blank"
            rel="noopener noreferrer"
          >
            <img
              src="/blog/dflieb-company-brain.png"
              alt="Tweet from David Lieb (@dflieb): “It's so nice having our YC company brain have access to slack, so I can use my agent to….search slack.”"
              className="mx-auto w-full max-w-[540px] rounded-xl border border-border-subtle"
            />
          </a>
          <p className="text-[14px] italic text-muted">
            One example of a guy using a company brain
          </p>

          <h2>How to actually build a company brain</h2>
          <p>
            Now that I&rsquo;ve given some motivation for why you should probably
            build a company brain, I will give a bunch of advice on how to
            actually do it.
          </p>

          <h3>
            Authentication: build a central control plane to handle different
            varieties of integration
          </h3>
          <p>
            A good company brain connects your AI agents to dozens of
            integrations. Most company brains today grow organically, one
            integration at a time, and thus have poor abstractions for handling
            large numbers of integrations. For example, hardcoding{" "}
            <code>client_id</code>s for integrations in environment variables is
            fine until you have 50 of them. This gets even more complicated when
            you start to incorporate integrations with different auth strategies;
            for example, MCP integrations such as Granola commonly use{" "}
            <Lnk href="https://datatracker.ietf.org/doc/html/rfc7591">
              Dynamic Client Registration
            </Lnk>
            , in which a client needs to be programmatically
            created at connection time per-user and therefore can&rsquo;t reliably
            be stored in an environment variable at all!
          </p>
          <p>
            Create a central DB table for company brain integrations once you
            start building (or at least migrate over to using them once
            you&rsquo;re ready). Store <code>client_id</code>, bearer auth token,
            and refresh token. This will cover all three common auth
            strategies&mdash;OAuth, API token, and DCR&mdash;so you won&rsquo;t
            have to continually rebuild your authentication infra as you add on
            more and more integrations. Encrypt these fields in this DB at rest
            unless you want your CISO to get mad at you.
          </p>
          <img
            src="/blog/integrations-auth-table.png"
            alt="A central integrations table storing encrypted client_id, client_secret, bearer auth token, and refresh token per integration (Jira and Granola shown)."
            className="w-full rounded-xl border border-border-subtle"
          />
          <p className="text-[14px] italic text-muted">
            Example of what your integrations table might look like
          </p>

          <h3>Give your AI great retrieval and memory</h3>
          <p>
            These integrations are only useful if your agent is able to easily
            find the information inside them. We do two things in order to make it
            easy for agents to find information in company resources: (1) we
            regularly sync the information from integrations to your own database
            so that we aren&rsquo;t bottlenecked on API rate limits for querying,
            and (2) we build{" "}
            <Lnk href="https://www.letta.com/blog/sleep-time-compute/">
              sleep-time compute
            </Lnk>{" "}
            indexes on top of the data in order to facilitate faster and more
            relevant AI retrieval. I&rsquo;ll
            talk about both of these systems in a bit more detail below.
          </p>

          <h3>Syncing information</h3>
          <p>
            We use{" "}
            <Lnk href="https://docs.celeryq.dev/en/stable/getting-started/introduction.html">
              Celery
            </Lnk>{" "}
            to sync all integrations every hour. We&rsquo;ll also
            manually re-sync integrations whenever an AI agent writes a query that
            needs up-to-date information from a given source. There are some
            sources, like Slack and GitHub, which thankfully have great webhooks,
            so we can keep our synced data completely real-time up-to-date.
          </p>

          <h3>Build indexes on top of information</h3>
          <p>
            There was this{" "}
            <Lnk href="https://www.letta.com/blog/sleep-time-compute/">
              great paper
            </Lnk>{" "}
            that Letta put out last year that showed the usefulness of asking LLMs
            to precompute answers to questions that they anticipate the user will
            ask
            <Fnref id="1" />. We adapt this technique to improve
            the quality of information that AI agents are able to get out of our
            company brain.
          </p>
          <p>
            A great canonical spec of this is Andrej Karpathy&rsquo;s{" "}
            <Lnk href="https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f">
              LLM wiki
            </Lnk>
            . The essential idea is that you write a bunch of markdown documents
            summarizing the contents of the resources in your company brain. Be
            advised, though, that if you follow this implementation exactly, the
            LLM wiki will probably become &ldquo;slopified&rdquo; over time, as
            continual AI rewriting of a knowledge base causes it to lose
            information.
          </p>
          <p>
            We use a number of techniques to mitigate this such as periodic
            regeneration from source and citation requirements.
          </p>
          <p>
            However, in general this is an open problem. We&rsquo;re releasing a
            benchmark in the coming weeks to encourage creative solutions to the
            &ldquo;wiki slopification&rdquo; problem from the community.
          </p>
          <p>
            <em>
              If you&rsquo;re curious, I write about our indexing strategy in much
              more detail{" "}
              <Lnk href="https://x.com/henrytdowling/status/2054246434506199529">
                here
              </Lnk>
              .
            </em>
          </p>

          <h3>Store HTML data that your agents create</h3>
          <p>
            AI agents can give you much more expressive responses when they
            respond to your questions with an HTML document rather than a plain
            text response.{" "}
            <Lnk href="https://x.com/trq212/status/2052809885763747935">
              Here&rsquo;s
            </Lnk>{" "}
            a good article explaining the many reasons why. Below is a screenshot
            of such a document:
          </p>
          <img
            src="/blog/gong-data-retention-report.png"
            alt="An HTML report an agent produced from Gong sales-call data: “How often is data retention coming up in sales calls?” with summary stats and a weekly-mentions chart."
            className="w-full rounded-xl border border-border-subtle"
          />
          <p>
            In most company brain setups, after an agent creates one of these HTML
            documents, it is promptly thrown away. We think you should{" "}
            <strong>store these documents in your company brain,</strong> since
            they typically provide useful analysis on questions that are important
            to your business. We built a Claude Code plugin that automatically
            uploads these artifacts to the company brain after every conversation.
          </p>

          <h3>Upload your session transcripts</h3>
          <p>
            Similarly, perhaps more importantly, you should upload agent session
            transcripts to your company brain! AI agent transcripts are a gold
            mine of learnings, decisions, and synthesis, and they will only
            increase in their information contents as agents become capable of
            running on{" "}
            <Lnk href="https://metr.org/time-horizons/">
              increasingly long time horizons
            </Lnk>
            . I&rsquo;ve written about the importance of doing this{" "}
            <Lnk href="https://henrydowling.com/agent-velocity.html">previously</Lnk>
            &mdash;we found that giving
            agents access to their past session transcripts can reduce the amount
            of time they waste on coding tasks by nearly half!
          </p>
          <img
            src="/blog/transcript-sharing-benchmark.png"
            alt="Bar chart, “Claude Code arrives at the fix faster with transcript sharing”: tool calls 272 → ~137, agent turns 123 → ~71, and wasted actions 192 → ~5 when transcripts are shared."
            className="mx-auto w-full max-w-[560px] rounded-xl border border-border-subtle"
          />
          <p className="text-[14px] italic text-muted">
            Coding agents write higher quality code faster when they&rsquo;re able
            to read past transcripts. So you should make them accessible via your
            company brain!
          </p>
          <p>
            You can store session transcripts in a table, where each line from the{" "}
            <code>.jsonl</code> session transcript is a row.
          </p>

          <h3>User-scope data that you connect</h3>
          <p>
            One barrier to building a good company brain is that making it
            multiplayer requires careful consideration of privacy. You want
            everyone&rsquo;s agents to be able to benefit from a company brain,
            but you don&rsquo;t want anyone&rsquo;s agents to access any resources
            that they don&rsquo;t have access to.
          </p>
          <p>
            The simplest and most straightforward way to solve this is to simply
            user-scope all integrations&mdash;everyone in your organization has to
            individually connect all their company resources to the company brain.
            The general principle should be that{" "}
            <strong>
              each person&rsquo;s AI agent is only able to see the resources that
              they have direct OAuth access to view
            </strong>
            .
          </p>
          <p>
            This allows you to take advantage of the existing privacy controls
            built into your company resources rather than trying to re-invent
            access policies from scratch. I&rsquo;d recommend against re-inventing
            them, since it&rsquo;s pretty costly if you get it wrong (what if
            someone finds out they&rsquo;re getting fired because their AI agent
            mistakenly had access to a sensitive meeting transcript?).
          </p>

          <h2>Okay, now go build it!</h2>
          <p>
            What I wrote above is the SOTA for building a company brain in June
            2026. If you do these things, then you will be ahead of 95% of your
            competitors in terms of the AI adoption of your company, and you will
            find that you&rsquo;re able to get much higher quality work done, much
            faster than before. Happy building!
          </p>
          <p>
            Also, if you&rsquo;re interested in trying a service that provides the
            above for you out of the box, I&rsquo;d suggest you take a look at{" "}
            <Link
              href="/"
              className="font-medium text-brand underline underline-offset-4"
            >
              Stash
            </Link>
            ! We&rsquo;re fully open-source and our customers trust us to handle
            the annoying parts of getting their company brain up and running so
            they can skip right to the incredible benefits that they provide.
          </p>

          <hr />

          <ol className="text-[14px] text-dim">
            <li id="fn-1">
              This is basically the LLM version of caching; instead of
              deterministically precomputing and storing answers to compute-heavy
              questions, we just nondeterministically write up a summary distilling
              an answer to a question that we expect the user to likely ask.
            </li>
          </ol>
        </div>

        <div className="mt-12">
          <Link
            href="/blog"
            className="text-[14px] font-medium text-brand underline underline-offset-4 transition hover:text-ink"
          >
            &larr; Back to blog
          </Link>
        </div>
      </article>
    </main>
  );
}

function Fnref({ id }: { id: string }) {
  return (
    <a
      href={`#fn-${id}`}
      className="font-medium text-brand no-underline align-super text-[12px]"
    >
      [{id}]
    </a>
  );
}

function Lnk({
  href,
  children,
}: {
  href: string;
  children: React.ReactNode;
}) {
  return (
    <a
      href={href}
      target="_blank"
      rel="noopener noreferrer"
      className="font-medium text-brand underline underline-offset-4 transition hover:text-ink"
    >
      {children}
    </a>
  );
}

function Header() {
  return (
    <header className="sticky top-0 z-30 border-b border-border-subtle bg-background/85 backdrop-blur">
      <div className="mx-auto flex h-16 max-w-[1200px] items-center justify-between px-7">
        <Link
          href="/"
          className="font-display text-[20px] font-black tracking-[-0.03em] text-ink"
        >
          stash
        </Link>
        <nav className="flex items-center gap-5 text-[14px] text-dim">
          <Link href="/discover" className="transition hover:text-ink">
            Discover
          </Link>
          <Link href="/docs" className="transition hover:text-ink">
            Docs
          </Link>
          <Link href="/blog" className="text-ink">
            Blog
          </Link>
          <Link href="/contact-sales" className="transition hover:text-ink">
            Contact sales
          </Link>
          <Link
            href="/login"
            className="hidden h-10 items-center rounded-lg border border-border bg-background px-[18px] text-[14px] font-medium text-ink transition hover:border-ink sm:inline-flex"
          >
            Sign in
          </Link>
        </nav>
      </div>
    </header>
  );
}
