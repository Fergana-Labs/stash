import type { Metadata } from "next";
import Link from "next/link";

import SiteFooter from "../../_components/SiteFooter";
import SiteHeader from "../../_components/SiteHeader";
import { POSTS, blogPostingJsonLd } from "../_lib/posts";

export const metadata: Metadata = {
  alternates: { canonical: "/blog/why-memory-is-unsolved" },
  title: "Why Memory Is Unsolved · Stash",
  description:
    "Most memory systems are still retrieval under the hood, and today's benchmarks mostly measure retrieval. Why perfect search is not enough, and the two problems actually holding memory back: blast radius and stability.",
};

const X_POST = "https://x.com/samzliu/status/2103205751858844086";

export default function WhyMemoryIsUnsolvedPage() {
  const post = POSTS["why-memory-is-unsolved"];

  return (
    <main className="min-h-screen bg-background text-foreground">
      <script
        type="application/ld+json"
        dangerouslySetInnerHTML={{ __html: JSON.stringify(blogPostingJsonLd(post)) }}
      />
      <SiteHeader current="Blog" />

      <article className="mx-auto max-w-[720px] px-7 pb-24 pt-16">
        <h1 className="text-balance font-display text-[clamp(32px,4.4vw,52px)] font-medium leading-[1.06] tracking-[-0.03em] text-ink">
          Why Memory Is Unsolved
        </h1>
        <p className="mt-5 text-[14px] text-muted">
          By {post.author.name} ·{" "}
          <time dateTime={post.datePublished}>{post.byline}</time>
        </p>
        <p className="mt-2 text-[14px] text-muted">
          Originally published on <Lnk href={X_POST}>X</Lnk>.
        </p>

        <div className="prose prose-lg mt-10">
          <p>
            We often get asked: how is memory different from RAG? Retrieval-Augmented Generation
            (or RAG) was a buzzword in the pre-agent era of LLMs that created massive companies
            like Glean. Despite that word being phased out in more agent-native circles, it
            remains a dominant mental framework for most. And while those perpetually on Twitter
            have moved on to &ldquo;memory&rdquo; or more recently &ldquo;continual
            learning&rdquo;, the RAG question is a sharp one. Most memory systems are not that
            different from RAG under the hood. The advancements we have seen are not due to
            better methods for memory but because the models using them have gotten better.
          </p>

          <img
            src="/blog/memory-markdown-retrieval.webp"
            width={1164}
            height={782}
            loading="lazy"
            alt="A tweet quoting a new Google paper, SKILL.state, that proposes replacing growing agent transcripts with explicit state, with the reply: Oh look, a worse version of beads, a full year later."
            className="mx-auto w-full rounded-xl border border-border-subtle"
          />
          <p className="text-[14px] italic text-muted">
            2026 memory systems don&rsquo;t look that different from ones of yesteryear: retrieval
            over a set of markdown files.
          </p>

          <p>
            They are still essentially a form of retrieval over a corpus of text. The exact
            retrieval mechanism and background architecture may vary: grep over a file system of
            markdown files, knowledge graphs, vector search + BM25 with reranking, etc. However,
            they are all functionally the same: better search. The claim we make here is that
            perfect retrieval is not enough to solve the &ldquo;memory&rdquo; or &ldquo;continual
            learning&rdquo; problem. Solving this requires a paradigm shift over what memory
            actually is and the role it plays within agentic systems.
          </p>
          <p>
            Memory is clearly an important problem at the moment. We see companies building
            their own{" "}
            <Lnk href="https://x.com/cerebras/status/2077822555159945507">context layer</Lnk>,{" "}
            <Lnk href="https://www.youtube.com/watch?v=WWUB9W5pl2w">
              Astra&rsquo;s memory being reverse-engineered
            </Lnk>
            , and the rise of{" "}
            <Lnk href="https://x.com/ashwingop/article/2093026452929405356">Instinct</Lnk> being
            attributed to its memory system. At the core is the prevailing belief in the{" "}
            <Lnk href="https://alexzhang13.github.io/blog/2026/mgh/">
              mis-managed genius hypothesis
            </Lnk>
            : the idea that modern models can do almost any task if you provide them the right
            context or harness.
          </p>
          <p>
            It&rsquo;s also apparent to anyone who has used agents that memory is still unsolved.
            You cannot treat a modern agent like you would a normal human. The barrier is that{" "}
            <Lnk href="https://www.engramme.com/index/memory-is-not-search">
              memory is not retrieval
            </Lnk>
            , but the entire ecosystem still treats it largely like a retrieval or search
            problem.
          </p>

          <h2>Existing benchmarks are insufficient</h2>
          <p>
            Benchmarks and evals are likely the most important part of any AI system. Having one
            means you can hill-climb against it and eventually solve it. Without a good
            benchmark, it is hard to make progress.
          </p>
          <p>
            The issue is that all of the existing popular benchmarks such as LoCoMo, LongMemEval,
            or BEAM 10M are largely sophisticated versions of the needle-in-the-haystack problem:
            find the right information (or lack thereof) in a large corpus. This is essentially
            retrieval. Agents have saturated many of these benchmarks and yet memory
            doesn&rsquo;t feel qualitatively better.
          </p>
          <p>
            One main issue here is that needle-in-the-haystack problems are only a small
            component of what it means to remember things. Most of your day-to-day isn&rsquo;t
            about struggling to think back to remember a distant memory in the past. Instead,
            it&rsquo;s about what you expect to happen based on an internal model of the world.
            Memory in this sense is a &ldquo;world model&rdquo; that is merely grounded in the
            past rather than <em>of the past</em>, which helps you make better decisions.
          </p>
          <p>
            The implication is that most memory benchmarks are measuring the wrong thing. They
            emphasize good search over large corpuses that contain sparse signals, while most
            day-to-day memory use cases relate to more frequently occurring tasks and insights.
            They ignore the time-dependent process of a memory system evolving over time in favor
            of a single static corpus to ask questions against. As we&rsquo;ll see later, this is
            a critical barrier to good memory systems today.
          </p>
          <p>
            Memory benchmarks are also hard to build because they inherently involve large
            corpuses or long-horizon tasks. This creates a three-fold problem: 1) it is hard to
            curate the benchmarks in sufficient quantity to have good statistical power, 2) it is
            expensive to run the benchmark, and 3) it is hard to perform credit assignment to
            hill-climb. As models become better, this is ever more important. LoCoMo, the most
            popular memory benchmark, is largely useless today because its largest corpus is
            &lt;1M tokens. This means a modern frontier model can fit the corpus into its context
            window and saturate the benchmark. (NB —{" "}
            <Lnk href="https://samzliu.substack.com/p/why-context-windows-wont-save-us">
              this does not mean context windows will solve the memory problem
            </Lnk>
            .) The strength of modern methods combined with the compound nature of memory systems
            also means it is hard to evaluate like-for-like. Using a strong frontier model vs a
            weaker last-generation model can sometimes swing the benchmarks 10–15% even with no
            other changes made. However, companies reporting benchmark results rarely report what
            models were used in their proprietary system. Each benchmark also tends to emphasize
            different failure modes, from abstentions to multi-hop questions. It&rsquo;s easy to
            build a memory system which performs well on one of these benchmarks at the expense
            of the others or real-life user performance.
          </p>
          <p>
            These benchmarks are not completely useless though. They do a good job of testing for
            retrieval quality. They are a necessary but insufficient step to solving memory. Due
            to modern context windows, we believe that the only really meaningful ones today are
            BEAM 10M and LongMemEval-v2, both of which have corpuses beyond a modern frontier
            model&rsquo;s context window. However, as the data generated by agents increases,
            these are not sufficient. BEAM 10M conversations are only about 10M tokens in length.
            For context, that is less than the amount of tokens our intern generated in his week
            of using Claude Code with us.
          </p>

          <img
            src="/blog/intern-token-count.webp"
            width={1198}
            height={128}
            loading="lazy"
            alt="Terminal output summarizing one week of Claude Code transcripts: about 6.7M tokens of message text plus 7.6M tokens of tool results, roughly 14M tokens combined."
            className="mx-auto w-full rounded-xl border border-border-subtle"
          />
          <p className="text-[14px] italic text-muted">
            He generated 14M tokens in 1 week. Modern benchmarks are not enough.
          </p>

          <h2>Near perfect on the STALE benchmark</h2>
          <p>
            To explain this point on benchmarks further, we show that we were able to essentially
            saturate the <Lnk href="https://arxiv.org/abs/2605.06527">STALE benchmark</Lnk>,
            which was released only in May 2026.
          </p>

          <img
            src="/blog/stale-benchmark-paper.webp"
            width={1634}
            height={670}
            loading="lazy"
            alt="Diagram from the STALE paper: a user mentions biking to work, later breaks their leg playing basketball, and the memory system must infer the hidden conflict so it no longer assumes the user bikes to work."
            className="mx-auto w-full rounded-xl border border-border-subtle"
          />
          <p className="text-[14px] italic text-muted">Taken from arXiv:2605.06527.</p>

          <p>
            The benchmark measures an important failure mode of memory around staleness: existing
            facts are often invalidated by seemingly unrelated new facts. For example, if you
            break your leg, that may mean you can no longer bike to work. However, biking to work
            is largely unrelated to breaking your leg at the semantic level, so most memory
            systems would not be able to pick up on this.
          </p>
          <p>
            Gemini 3.1 Pro was only able to achieve 55.2%, while the authors&rsquo; custom system
            achieved 68%. Our system achieved ~95.6%, or ~99.4% if you allow for a bit of
            benchmax prompting (with the caveat that we only ran this on random samples
            containing 15% of the full benchmark for speed reasons; we believe this is enough
            statistical power to make our point).
          </p>

          <img
            src="/blog/stale-benchmark-results.webp"
            width={2496}
            height={1484}
            loading="lazy"
            alt="Bar chart of Stash pass rates on STALE: overall 97.78% on direct updates and 93.33% on indirect updates, with every category between 90% and 100%."
            className="mx-auto w-full rounded-xl border border-border-subtle"
          />
          <p className="text-[14px] italic text-muted">
            Blended average of 95.6% over T1 and T2 questions.
          </p>

          <p>
            To reach this number, we modified our existing memory system in a very simple way:
            each piece of information ingested into the system also became a query. We then
            updated the returned results based on the new ingested information. For example, if
            we inserted the information that the user broke their leg, our query would look for
            and find related, stored information about topics like user health. This would
            enable it to find and then update the piece on bike commuting.
          </p>
          <p>
            However, it&rsquo;s unclear whether this change would cause any downstream effects
            on other types of failure modes. For instance, this may muddle the memory store for
            multi-hop questions. Ultimately, this goes beyond the standard benchmaxxing concerns:
            these benchmarks disguise a vibes-based memory approach as an objective benchmark.
            The benchmark itself may be a reasonable measurement under ideal conditions, but what
            the authors choose to measure is mostly a subjective judgement call. More often than
            not, that subjective call turns into a retrieval rather than a memory benchmark.
          </p>

          <h2>
            What memory requires beyond retrieval: why agentic scaling over search and
            integrations is not sufficient
          </h2>
          <p>
            Another common refrain we hear is that agentic grep + integrations with data is
            sufficient for a good memory system. This is not true. To see this, imagine an agent
            running on the next generation of Astra, but its only memory system is keyword search
            over a corpus the size of the entire internet. Obviously, this would present some
            issues. It would likely take too long and cost too much to find anything useful.
            Moreover, there&rsquo;s a high likelihood such an agent wouldn&rsquo;t be able to
            find the relevant information at all. As the data corpus from agents becomes larger,
            these concerns are very real. It&rsquo;s simply not feasible for an agent to search
            over the entire corpus every time. We also see decreasing performance as corpus size
            grows.
          </p>

          <img
            src="/blog/grep-corpus-scaling.webp"
            width={1446}
            height={984}
            loading="lazy"
            alt="Line chart of BEAM score against corpus size from 100K to 10M tokens: the grep baseline falls from 0.72 to 0.53, while Stash declines least, from 0.80 to 0.73, ahead of Exabase M-1, Hindsight, and Honcho."
            className="mx-auto w-full rounded-xl border border-border-subtle"
          />
          <p className="text-[14px] italic text-muted">
            Traditional agentic grep performance falls rapidly as corpus size increases.
          </p>

          <p>
            In particular, search is a problem that scales with the size of the corpus. An ideal
            memory system does not. Instead, it scales to the size of the problem by presenting
            the agent with the right information for the task at hand. A very experienced chess
            player doesn&rsquo;t have a harder time finding previous chess positions that are
            similar to the current board compared to an intermediate player. They have an easier
            time. This means that thinking of memory systems as simply an index or a cache over
            an agentic search process is limiting. There are three things beyond search and
            retrieval which a memory system has to do:
          </p>
          <ul>
            <li>
              <strong>Synthesis.</strong> Developing an integrated model of the world is
              important for a memory system. It has to combine different threads into a coherent
              picture which the agent can then pull from.
            </li>
            <li>
              <strong>Proactive push.</strong> It&rsquo;s not sufficient to have the agent decide
              when it needs to find something. Instead, relevant information has to be pushed to
              the agent when it is useful. Otherwise, how could the agent know to even begin a
              search?
            </li>
            <li>
              <strong>Metadata.</strong> The important pieces of information are often the
              commentary instead of the underlying data itself. As an example, the nuances of the
              exceptions and process around a database table and its schema are needed to do any
              proper analysis.
            </li>
          </ul>

          <h2>The two key problems holding memory back</h2>
          <p>
            If retrieval is mostly solved, what is the bottleneck to memory then? We believe that
            there are two main ones:
          </p>
          <ul>
            <li>
              <strong>Blast radius.</strong> A generalization of the staleness problem from
              above. Information is bounded by time, scope, or priority. For instance, you can
              scroll through Instagram ads without letting them affect you (that much), but this
              is much harder for an agent that needs to reason about whether that information is
              applicable. Methods such as constitutional AI help, but they are limited in scope.
              Humans do this kind of implicit prioritization fluidly across many dimensions.
            </li>
            <li>
              <strong>Stability.</strong> As corpuses grow larger, an agent needs to have a stable
              view of the world and the past to behave reliably and effectively. The standard
              retrieval problem is too stochastic over large corpuses, while maintaining a world
              model of sorts can lead to regression toward the mean and agent slop very quickly.
            </li>
          </ul>
          <p>
            Internally, we have developed evaluations to enable hill-climbing on each of these.
            We measure blast radius with evals focused on its two sides: when an agent fails to
            consider a piece of information as relevant even though it is (e.g. the bike vs
            broken leg problem above), and when an agent over-extends the blast radius of some
            information (e.g. the advertising example). On stability, we believe in more of a
            world-modeling approach over unbounded search. Thus, we can measure stability through
            a &ldquo;PCR-like&rdquo; approach: iteratively update our memory store in place many
            times. This amplifies any slop created through the process and makes measuring it
            much easier. Through these two eval methods, we&rsquo;ve been able to make our memory
            system behave more naturally than benchmarking over retrieval alone would allow.
          </p>
          <p>
            Despite the interest in memory, there are still many unsolved problems! If you have
            been building or thinking about memory, please{" "}
            <Lnk href="https://x.com/samzliu">send over a DM</Lnk> or{" "}
            <Link href="/contact-sales">book a call</Link>.
          </p>
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
      className="text-brand underline underline-offset-4 transition hover:text-ink"
    >
      {children}
    </a>
  );
}
