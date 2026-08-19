import type { Metadata } from "next";
import Link from "next/link";

import SiteFooter from "../../_components/SiteFooter";
import SiteHeader from "../../_components/SiteHeader";
import { POSTS, blogPostingJsonLd } from "../_lib/posts";

export const metadata: Metadata = {
  alternates: { canonical: "/blog/open-questions-in-memory" },
  title: "Open Questions in Memory, and Our Predictions · Stash",
  description:
    "The questions we argue about most with others building AI memory — labs vs startups, weight vs token space, retrieval vs blast radius, benchmarks, context windows — and where we think each one lands.",
};

const X_POST = "https://x.com/samzliu/status/2075737137341940098";

export default function OpenQuestionsInMemoryPage() {
  const post = POSTS["open-questions-in-memory"];

  return (
    <main className="min-h-screen bg-background text-foreground">
      <script
        type="application/ld+json"
        dangerouslySetInnerHTML={{ __html: JSON.stringify(blogPostingJsonLd(post)) }}
      />
      <SiteHeader current="Blog" />

      <article className="mx-auto max-w-[720px] px-7 pb-24 pt-16">
        <p className="flex items-center font-mono text-[11px] font-medium uppercase tracking-[0.14em] text-muted">
          <span className="mr-[10px] inline-block h-[6px] w-[6px] rounded-full bg-brand" />
          Blog
        </p>
        <h1 className="mt-5 text-balance font-display text-[clamp(32px,4.4vw,52px)] font-medium leading-[1.04] tracking-[-0.035em] text-ink">
          Open Questions in Memory, and Our Predictions
        </h1>
        <p className="mt-5 text-[14px] text-muted">
          By {post.author.name} ·{" "}
          <time dateTime={post.datePublished}>{post.byline}</time>
        </p>
        <p className="mt-2 text-[14px] text-muted">
          Cross-posted from <Lnk href={X_POST}>X</Lnk>. We&rsquo;d love to hear
          your predictions and disagreements &mdash; reply there.
        </p>

        <div className="prose prose-lg mt-10">
          <p>
            One of the beautiful things about building in a new space is that
            there are no right answers yet. This also means that to build
            anything inherently involves making bets on where the ecosystem will
            evolve. We&rsquo;ve compiled a (non-exhaustive) list below of
            questions that we discuss often with those in this space along our
            predictions on what the answer is. We would love to hear your
            thoughts, predictions, and disagreements!
          </p>

          <h2>
            Is there room for memory and knowledge base companies beyond the
            labs?
          </h2>
          <p>
            <strong>Prediction:</strong>&nbsp;Companies doing vertical memory scaling
            (i.e. helping agents run for longer) will have a hard time competing
            and will be squeezed by the labs and other agentic harnesses.
            Companies doing horizontal scaling (i.e. across teams or entire
            organizations) will find a better landscape. This is because
            enterprise deal cycles take longer and the problems (data isolation,
            security, company ontology) cannot be solved by the newest model
            update or research idea.
          </p>

          <h2>Should memory layers operate in weight vs token space?</h2>
          <p>
            Token space has a lot of advantages. It&rsquo;s interpretable.
            It&rsquo;s model-agnostic. It&rsquo;s cheap. We have decades of
            infrastructure built to handle storage, data isolation, modularity,
            etc.
          </p>
          <p>
            Weight however seems to be more expressive and there may be a class
            of problems that we cannot solve purely in token space. In
            particular, procedural memory involving fuzzy lines and complex
            branching paths do not seem well suited for token space (e.g. think
            of trying to read the rules to a board game vs being shown how to
            play it).
          </p>
          <p>
            <strong>Prediction:</strong>&nbsp;Most memory will operate in token space
            (e.g. agent traces, semantic information, etc.) but there will be
            certain problems (e.g. writing style, taste, procedural skills,
            etc.) that will have adapters which can be fit into models. Mech
            interp techniques will enable us to interpret them.
          </p>

          <h2>Is memory simply a search and retrieval problem?</h2>
          <p>
            Most memory systems today are focused on retrieval. They are focused
            on finding the right information at the right time for agents to do
            work (e.g. LoCoMo benchmark focuses on needle in the haystack
            retrieval).
          </p>
          <p>
            The question is if this is sufficient to solve the memory problem.
            Put it another way, if you hook on SOTA search (e.g. Google or Exa
            or Perplexity) to a private data store, is that enough to call
            memory solved?
          </p>
          <p>
            <strong>Prediction:</strong>&nbsp;There is a growing consensus of
            researchers and builders working at the cutting edge that memory is
            not merely storage of information and retrieval over that
            information. We call this problem &ldquo;blast radius&rdquo;
            internally. Information&rsquo;s usefulness is bounded by scope (time
            or context). Humans have no problem reading tons of irrelevant text
            and only applying the proper weight to the most useful information.
            A pure retrieval system (even with smart reranking) falls short of
            that.
          </p>

          <h2>Should we inject information into context automatically?</h2>
          <p>
            The argument against is context rot or pollution. Injecting
            information into an agent, especially if it is not the right
            information could cause degraded performance. It also causes the
            agent to over index on connections between your sessions which may
            not actually be real. This is why many people turn off memory
            features for ChatGPT or Claude Code.
          </p>
          <p>
            <strong>Prediction:</strong>&nbsp;Injecting information into context is
            critical because it enables the agent to deal with &ldquo;unknown
            unknowns&rdquo;. You can have a perfect memory tool but if the agent
            doesn&rsquo;t know to use it, you haven&rsquo;t solved the problem.
            For humans, this type of &ldquo;injection&rdquo; happens all the
            time. Past memories appear in your consciousness without your active
            choice. The problems with this today are likely downstream from the
            blast radius problem outlined above.
          </p>

          <h2>What are the right benchmarks for memory?</h2>
          <p>
            There is a general sense that existing benchmarks like LoCoMo and
            LongMemEval are not sufficient. We&rsquo;ve hit on ~85% performance
            on them and memory still feels as unsolved today as it did a year
            ago. Moreover, better performance on the benchmarks doesn&rsquo;t
            seem to correlate with &ldquo;better feeling&rdquo; memory from a
            user perspective.
          </p>
          <p>
            Moreover, benchmarks in this space are difficult build since the
            inherently long time horizons memory operates over create data
            availability and cost/scaling problems.
          </p>
          <p>
            <strong>Prediction:</strong>&nbsp;The company or lab that solves this
            problem will likely not do so by hill climbing on a benchmark but by
            betting on some customer/user insight that current benchmarks are
            not measuring. This is similar to Wispr Flow where they threw out
            the word-error-rate metric that other transcription tools anchored
            on.
          </p>

          <h2>Will longer context windows solve everything?</h2>
          <p>
            We made a prediction in Jan that context windows won&rsquo;t
            actually solve the problem and it has turned out to be mostly right
            so far.
          </p>

          <h2>
            Strong models combined with data integrations make memory systems
            useless
          </h2>
          <p>
            The argument for is that you can retrieve any information you want
            if you have a frontier model + agent harness + MCP data connectors.
            And it turns out that the retrieval quality doesn&rsquo;t change
            much compared to other systems (e.g. LLM wiki, hybrid retrieval,
            etc.)
          </p>
          <p>
            <strong>Prediction:</strong>&nbsp;In the short term, memory systems are
            still useful because they reduce latency and cost compared to having
            frontier models search over everything all the time. In the medium
            to long term, memory systems enable consistency over retrievals
            which enable compounding. Put it another way, we still have agents
            write code which they improve over time rather than have them
            manifest say an app directly.
          </p>

          <h2>Agentic search over file systems are all you need</h2>
          <p>
            Letta predicted this last year and it has turned out to be quite
            prophetic. In the short-medium term, agents are extremely good at
            operating over file systems due to the post-training aimed at coding
            performance. Leveraging that post-training yields rewards today.
          </p>
          <p>
            <strong>Prediction:</strong>&nbsp;In the long term, it&rsquo;s hard not
            to imagine a type hybrid index in addition to a file system. The
            main intuition behind why this is necessary is that file systems
            perform worse in when there are higher volumes of data or in
            federated use-cases. Agent &ldquo;monologues&rdquo; over raw data
            will also become increasingly important and we will need principled
            and structured ways to support that.
          </p>
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


      <SiteFooter />
    </main>
  );
}

function Lnk({ href, children }: { href: string; children: React.ReactNode }) {
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

